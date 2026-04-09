"""
MM Exit Guard — Greatest MM Fill Profit-Take Watchdog
======================================================

PURPOSE:
  After any GREATEST_MM INC fill (≥200 lots), ensures there is ALWAYS
  a corresponding profit-take exit order on the opposite side.

  LONG INC fill  →  must have a SELL order ≥ fill_price + $0.07
  SHORT INC fill →  must have a BUY  order ≤ fill_price - $0.07

  If no such exit order exists AND no REV order covers it,
  this guard creates a HIDDEN LIMIT exit order.

RULES:
  1. Minimum 200 lot filled → triggers guard
  2. Check open orders for opposite-side exit within profit threshold
  3. Check if REV order already exists for this symbol
  4. If neither found → place HIDDEN LIMIT profit-take order
  5. Pricing: fill_price ± 0.07 (minimum), prefer better if spread allows
  6. Runs inside RUNALL cycle or as periodic check (every 30s)

ACCOUNT ISOLATION:
  All tracking is per-account. HAMPRO and IBKR_PED fills are stored
  separately in Redis and checked independently. Same symbol in two
  accounts = two separate tracked fills.

TAGS:
  MM_EXIT_GUARD_SELL  (profit-take for long fill)
  MM_EXIT_GUARD_BUY   (profit-take for short fill)
"""

import json
import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field

from app.core.logger import logger
from app.core.redis_client import get_redis_client


# ============================================================================
# CONFIGURATION
# ============================================================================

MIN_FILL_LOT = 200           # Minimum fill qty to trigger guard
MIN_PROFIT_CENTS = 0.07      # $0.07 = 7 cents minimum profit target
GUARD_CHECK_INTERVAL = 30    # Check every 30 seconds
REDIS_GUARD_TTL = 86400      # 24h TTL for tracked fills

# Don't re-check fills older than this (already handled or expired)
MAX_FILL_AGE_SECONDS = 8 * 3600  # 8 hours (full trading day)


def _redis_key(account_id: str) -> str:
    """Per-account Redis key for tracked fills."""
    return f"mm_exit_guard:tracked_fills:{account_id}"


def _tracking_key(account_id: str, symbol: str) -> str:
    """Composite key: {account}:{symbol} — ensures account-level isolation."""
    return f"{account_id}:{symbol}"


# ============================================================================
# FILL RECORD
# ============================================================================

@dataclass
class TrackedFill:
    """A GREATEST_MM fill being tracked for exit guard."""
    symbol: str
    action: str                # 'BUY' (long inc) or 'SELL' (short inc)
    fill_price: float
    fill_qty: int
    fill_ts: float             # Unix timestamp
    account_id: str
    tag: str = ""              # Original order tag
    exit_order_placed: bool = False
    exit_order_price: float = 0.0
    guard_check_count: int = 0
    
    @property
    def is_long(self) -> bool:
        return self.action.upper() == 'BUY'
    
    @property
    def is_short(self) -> bool:
        return self.action.upper() == 'SELL'
    
    @property
    def required_exit_action(self) -> str:
        """What action the exit order must be."""
        return 'SELL' if self.is_long else 'BUY'
    
    @property
    def min_exit_price(self) -> float:
        """Minimum acceptable exit price for profit."""
        if self.is_long:
            return round(self.fill_price + MIN_PROFIT_CENTS, 2)
        else:
            return round(self.fill_price - MIN_PROFIT_CENTS, 2)
    
    @property
    def age_seconds(self) -> float:
        return time.time() - self.fill_ts
    
    @property
    def tracking_key(self) -> str:
        return _tracking_key(self.account_id, self.symbol)
    
    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'action': self.action,
            'fill_price': self.fill_price,
            'fill_qty': self.fill_qty,
            'fill_ts': self.fill_ts,
            'account_id': self.account_id,
            'tag': self.tag,
            'exit_order_placed': self.exit_order_placed,
            'exit_order_price': self.exit_order_price,
            'guard_check_count': self.guard_check_count,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TrackedFill':
        return cls(
            symbol=data.get('symbol', ''),
            action=data.get('action', ''),
            fill_price=float(data.get('fill_price', 0)),
            fill_qty=int(data.get('fill_qty', 0)),
            fill_ts=float(data.get('fill_ts', 0)),
            account_id=data.get('account_id', ''),
            tag=data.get('tag', ''),
            exit_order_placed=data.get('exit_order_placed', False),
            exit_order_price=float(data.get('exit_order_price', 0)),
            guard_check_count=int(data.get('guard_check_count', 0)),
        )


# ============================================================================
# MM EXIT GUARD ENGINE — ACCOUNT-ISOLATED
# ============================================================================

class MMExitGuard:
    """
    Watches GREATEST_MM INC fills and ensures exit orders exist.
    
    ACCOUNT ISOLATION:
      - _tracked dict uses composite key: "{account_id}:{symbol}"
      - Redis persistence is per-account: mm_exit_guard:tracked_fills:{account_id}
      - Open order lookups are per-account
      - Every operation requires account_id
    
    Flow:
      1. on_mm_fill() — called when GREATEST_MM fill detected
      2. check_all_fills() — periodic scan of tracked fills
      3. For each unguarded fill:
         a. Check if exit order exists (open orders from broker, same account)
         b. Check if REV order covers it (same account)
         c. If neither → create HIDDEN LIMIT exit
    """
    
    def __init__(self):
        self._redis = None
        # ACCOUNT-ISOLATED: composite key "{account}:{symbol}" → TrackedFill
        self._tracked: Dict[str, TrackedFill] = {}
        self._running = False
        logger.info("[MM_EXIT_GUARD] 🛡️ Initialized — account-isolated tracking for MM INC fills ≥200 lots")
    
    # =====================================================================
    # REDIS — PER-ACCOUNT PERSISTENCE
    # =====================================================================
    
    def _get_redis(self):
        if self._redis is None:
            client = get_redis_client()
            if client:
                self._redis = client.sync if hasattr(client, 'sync') else client
        return self._redis
    
    def _save_to_redis(self):
        """Persist tracked fills to Redis — per-account keys."""
        redis = self._get_redis()
        if not redis:
            return
        try:
            # Group fills by account
            by_account: Dict[str, Dict[str, str]] = {}
            for key, fill in self._tracked.items():
                acct = fill.account_id
                if acct not in by_account:
                    by_account[acct] = {}
                by_account[acct][fill.symbol] = json.dumps(fill.to_dict())
            
            # Write each account's fills to its own Redis key
            # Also collect all known accounts to clean up empty ones
            known_accounts = set(by_account.keys())
            
            # Check for previously known accounts that might now be empty
            for test_acct in ['HAMPRO', 'IBKR_PED', 'IBKR_GUN']:
                rkey = _redis_key(test_acct)
                if test_acct not in known_accounts:
                    # No fills for this account → clean up Redis key 
                    try:
                        redis.delete(rkey)
                    except Exception:
                        pass
            
            for acct, fills_map in by_account.items():
                rkey = _redis_key(acct)
                redis.delete(rkey)
                if fills_map:
                    redis.hset(rkey, mapping=fills_map)
                    redis.expire(rkey, REDIS_GUARD_TTL)
                    
        except Exception as e:
            logger.debug(f"[MM_EXIT_GUARD] Redis save error: {e}")
    
    def _load_from_redis(self):
        """Load tracked fills from Redis — all accounts."""
        redis = self._get_redis()
        if not redis:
            return
        try:
            for acct in ['HAMPRO', 'IBKR_PED', 'IBKR_GUN']:
                rkey = _redis_key(acct)
                raw = redis.hgetall(rkey)
                if not raw:
                    continue
                for sym_bytes, data_bytes in raw.items():
                    sym = sym_bytes.decode() if isinstance(sym_bytes, bytes) else sym_bytes
                    data_str = data_bytes.decode() if isinstance(data_bytes, bytes) else data_bytes
                    fill_data = json.loads(data_str)
                    fill = TrackedFill.from_dict(fill_data)
                    # Ensure account_id consistency
                    if not fill.account_id:
                        fill.account_id = acct
                    # Skip expired fills
                    if fill.age_seconds < MAX_FILL_AGE_SECONDS:
                        key = fill.tracking_key
                        self._tracked[key] = fill
            
            if self._tracked:
                # Group by account for logging
                acct_summary = {}
                for f in self._tracked.values():
                    acct_summary.setdefault(f.account_id, []).append(f.symbol)
                for acct, syms in acct_summary.items():
                    logger.info(
                        f"[MM_EXIT_GUARD] 🔄 Recovered {len(syms)} fills for {acct}: {syms}"
                    )
        except Exception as e:
            logger.debug(f"[MM_EXIT_GUARD] Redis load error: {e}")
    
    # =====================================================================
    # FILL REGISTRATION — ACCOUNT-ISOLATED
    # =====================================================================
    
    def on_mm_fill(
        self,
        symbol: str,
        action: str,
        fill_price: float,
        fill_qty: int,
        account_id: str,
        tag: str = "",
        source: str = ""
    ):
        """
        Called when a GREATEST_MM fill is detected.
        
        Only tracks INC fills (position increase) — these need profit-take exits.
        DEC fills are position reduces, handled by REV reload.
        
        Args:
            symbol: e.g. 'AFGB'
            action: 'BUY' or 'SELL'
            fill_price: actual fill price
            fill_qty: filled quantity
            account_id: 'HAMPRO' or 'IBKR_PED' — REQUIRED for isolation
            tag: order tag (e.g. 'MM_MM_LONG_INC')
            source: engine source name
        """
        if not account_id:
            logger.warning(f"[MM_EXIT_GUARD] ⚠️ Fill without account_id: {symbol} — skipping")
            return
        
        # Only track INC fills (increases)
        tag_upper = tag.upper()
        is_inc = 'INC' in tag_upper or 'INCREASE' in tag_upper
        
        # If tag is ambiguous, BUY = long increase, SELL = short increase for MM
        if not is_inc and 'DEC' not in tag_upper and 'DECREASE' not in tag_upper:
            is_inc = True  # Default to INC for ambiguous MM fills
        
        if not is_inc:
            logger.debug(
                f"[MM_EXIT_GUARD] Skipping DEC fill: {symbol} {action} {fill_qty}lot "
                f"@${fill_price:.2f} tag={tag} acct={account_id}"
            )
            return
        
        # Minimum lot check
        if fill_qty < MIN_FILL_LOT:
            logger.debug(
                f"[MM_EXIT_GUARD] Skipping small fill: {symbol} {action} {fill_qty}lot "
                f"(min={MIN_FILL_LOT}) acct={account_id}"
            )
            return
        
        # Composite tracking key — account-isolated
        key = _tracking_key(account_id, symbol)
        
        # Track this fill
        fill = TrackedFill(
            symbol=symbol,
            action=action.upper(),
            fill_price=fill_price,
            fill_qty=fill_qty,
            fill_ts=time.time(),
            account_id=account_id,
            tag=tag,
        )
        
        # If we already track this (same account + symbol), accumulate (same direction)
        existing = self._tracked.get(key)
        if existing and existing.action == fill.action and not existing.exit_order_placed:
            # Same direction in same account, accumulate qty
            existing.fill_qty += fill_qty
            # Update fill_price only if new one has a real price
            if fill_price > 0:
                existing.fill_price = fill_price
            existing.fill_ts = time.time()
            logger.info(
                f"[MM_EXIT_GUARD] 📊 [{account_id}] Accumulated: {symbol} {action} "
                f"total={existing.fill_qty}lot @${existing.fill_price:.2f} "
                f"| exit needed: {existing.required_exit_action} ≥${existing.min_exit_price:.2f}"
            )
        else:
            self._tracked[key] = fill
            logger.info(
                f"[MM_EXIT_GUARD] 🎯 [{account_id}] TRACKING: {symbol} {action} {fill_qty}lot "
                f"@${fill_price:.2f} | exit needed: {fill.required_exit_action} "
                f"≥${fill.min_exit_price:.2f} | tag={tag}"
            )
        
        self._save_to_redis()
    
    def on_exit_confirmed(self, symbol: str, account_id: str):
        """
        Called when exit order is confirmed placed for a symbol in a specific account.
        Marks the fill as guarded.
        """
        key = _tracking_key(account_id, symbol)
        if key in self._tracked:
            self._tracked[key].exit_order_placed = True
            self._save_to_redis()
            logger.info(f"[MM_EXIT_GUARD] ✅ [{account_id}] {symbol} exit order confirmed — guard satisfied")
    
    def on_position_closed(self, symbol: str, account_id: str):
        """
        Called when position is fully closed. Remove from tracking.
        """
        key = _tracking_key(account_id, symbol)
        if key in self._tracked:
            del self._tracked[key]
            self._save_to_redis()
            logger.info(f"[MM_EXIT_GUARD] 🗑️ [{account_id}] {symbol} position closed — removed from tracking")
    
    # =====================================================================
    # GUARD CHECK — finds unguarded fills and places exit orders
    # =====================================================================
    
    async def check_all_fills(self) -> List[Dict[str, Any]]:
        """
        Scan all tracked fills across all accounts and check for missing exit orders.
        Each fill is checked against its own account's open orders.
        
        Returns:
            List of exit orders that need to be placed.
        """
        if not self._tracked:
            return []
        
        orders_to_place = []
        keys_to_remove = []
        
        for key, fill in list(self._tracked.items()):
            try:
                # Skip if already guarded
                if fill.exit_order_placed:
                    continue
                
                # Skip if too old (expired)
                if fill.age_seconds > MAX_FILL_AGE_SECONDS:
                    logger.info(
                        f"[MM_EXIT_GUARD] ⏰ [{fill.account_id}] {fill.symbol} fill expired "
                        f"({fill.age_seconds/3600:.1f}h old) — removing"
                    )
                    keys_to_remove.append(key)
                    continue
                
                # Skip if fill_price is 0 (not yet updated with actual price)
                if fill.fill_price <= 0:
                    fill.guard_check_count += 1
                    if fill.guard_check_count <= 3:
                        logger.debug(
                            f"[MM_EXIT_GUARD] [{fill.account_id}] {fill.symbol} "
                            f"waiting for fill_price (check #{fill.guard_check_count})"
                        )
                    continue
                
                fill.guard_check_count += 1
                
                # Check if exit order already exists — IN SAME ACCOUNT
                has_exit = await self._check_exit_order_exists(
                    symbol=fill.symbol,
                    required_action=fill.required_exit_action,
                    min_price=fill.min_exit_price if fill.is_long else None,
                    max_price=fill.min_exit_price if fill.is_short else None,
                    account_id=fill.account_id,
                )
                
                if has_exit:
                    fill.exit_order_placed = True
                    logger.info(
                        f"[MM_EXIT_GUARD] ✅ [{fill.account_id}] {fill.symbol} already has exit order "
                        f"({fill.required_exit_action}) — guard satisfied"
                    )
                    continue
                
                # Check if REV order covers this fill — IN SAME ACCOUNT
                has_rev = await self._check_rev_order_exists(
                    symbol=fill.symbol,
                    required_action=fill.required_exit_action,
                    account_id=fill.account_id,
                )
                
                if has_rev:
                    fill.exit_order_placed = True
                    logger.info(
                        f"[MM_EXIT_GUARD] ✅ [{fill.account_id}] {fill.symbol} REV order exists — guard satisfied"
                    )
                    continue
                
                # ═══ NO EXIT ORDER FOUND — CREATE ONE ═══
                exit_order = await self._calculate_exit_order(fill)
                if exit_order:
                    orders_to_place.append(exit_order)
                    logger.warning(
                        f"[MM_EXIT_GUARD] ⚠️ [{fill.account_id}] {fill.symbol} NO EXIT ORDER! "
                        f"Fill: {fill.action} {fill.fill_qty}lot @${fill.fill_price:.2f} "
                        f"({fill.age_seconds:.0f}s ago) — CREATING exit: "
                        f"{exit_order['action']} @${exit_order['price']:.2f} "
                        f"(check #{fill.guard_check_count})"
                    )
                
            except Exception as e:
                logger.error(f"[MM_EXIT_GUARD] Error checking {key}: {e}")
        
        # Cleanup expired
        for k in keys_to_remove:
            del self._tracked[k]
        
        self._save_to_redis()
        return orders_to_place
    
    # =====================================================================
    # EXIT ORDER CHECK — per-account open orders from broker
    # =====================================================================
    
    async def _check_exit_order_exists(
        self,
        symbol: str,
        required_action: str,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        account_id: str = "",
    ) -> bool:
        """
        Check if there's already an open order that satisfies the exit requirement.
        ACCOUNT-SCOPED: only looks at orders in the specified account.
        
        For LONG fills: need SELL order at price ≥ fill + 0.07
        For SHORT fills: need BUY order at price ≤ fill - 0.07
        """
        try:
            # Get open orders — ONLY from this account
            open_orders = await self._get_open_orders(account_id)
            
            for order in open_orders:
                order_symbol = order.get('symbol', '')
                order_action = order.get('action', '').upper()
                order_price = float(order.get('price', 0))
                order_status = order.get('status', '').upper()
                
                # Skip non-matching or cancelled orders
                if order_symbol != symbol:
                    continue
                if order_action != required_action:
                    continue
                if order_status in ('CANCELLED', 'REJECTED', 'FILLED'):
                    continue
                
                # Check price threshold
                if min_price is not None and order_price >= min_price:
                    logger.debug(
                        f"[MM_EXIT_GUARD] [{account_id}] {symbol} found exit: "
                        f"{order_action} @${order_price:.2f} ≥ ${min_price:.2f}"
                    )
                    return True
                
                if max_price is not None and order_price <= max_price:
                    logger.debug(
                        f"[MM_EXIT_GUARD] [{account_id}] {symbol} found exit: "
                        f"{order_action} @${order_price:.2f} ≤ ${max_price:.2f}"
                    )
                    return True
            
            return False
            
        except Exception as e:
            logger.debug(f"[MM_EXIT_GUARD] Exit order check error for {account_id}:{symbol}: {e}")
            return False
    
    async def _check_rev_order_exists(
        self,
        symbol: str,
        required_action: str,
        account_id: str = "",
    ) -> bool:
        """
        Check if a REV order (TP type) already covers this symbol in this account.
        ACCOUNT-SCOPED: only checks orders from the specified account.
        """
        try:
            open_orders = await self._get_open_orders(account_id)
            
            for order in open_orders:
                order_symbol = order.get('symbol', '')
                order_action = order.get('action', '').upper()
                order_tag = order.get('tag', '').upper()
                order_status = order.get('status', '').upper()
                
                if order_symbol != symbol:
                    continue
                if order_status in ('CANCELLED', 'REJECTED', 'FILLED'):
                    continue
                
                # Check for REV_TP tag on same side
                if 'REV_TP' in order_tag and order_action == required_action:
                    logger.debug(
                        f"[MM_EXIT_GUARD] [{account_id}] {symbol} found REV_TP: "
                        f"{order_action} tag={order_tag}"
                    )
                    return True
                
                # Also check for any REV order on correct side
                if 'REV' in order_tag and order_action == required_action:
                    logger.debug(
                        f"[MM_EXIT_GUARD] [{account_id}] {symbol} found REV: "
                        f"{order_action} tag={order_tag}"
                    )
                    return True
            
            return False
            
        except Exception as e:
            logger.debug(f"[MM_EXIT_GUARD] REV check error for {account_id}:{symbol}: {e}")
            return False
    
    # =====================================================================
    # ORDER CALCULATION
    # =====================================================================
    
    async def _calculate_exit_order(self, fill: TrackedFill) -> Optional[Dict[str, Any]]:
        """
        Calculate exit order for an unguarded fill.
        
        LONG fill → SELL at max(fill + 0.07, ask - spread*0.15)
        SHORT fill → BUY at min(fill - 0.07, bid + spread*0.15)
        
        Always HIDDEN LIMIT.
        """
        symbol = fill.symbol
        
        # Get L1 data
        l1 = await self._get_l1_data(symbol)
        bid = l1.get('bid', 0)
        ask = l1.get('ask', 0)
        spread = ask - bid if ask > 0 and bid > 0 else 0.02
        
        if fill.is_long:
            # SELL to take profit on long
            min_target = fill.fill_price + MIN_PROFIT_CENTS
            
            # Prefer better price if L1 allows
            if ask > 0 and (ask - fill.fill_price) >= MIN_PROFIT_CENTS:
                # L1 ask is already at/above target — use ask - spread*0.15
                exit_price = round(ask - spread * 0.15, 2)
                if exit_price < min_target:
                    exit_price = min_target
                method = "L1_ASK"
            else:
                # L1 doesn't meet threshold — use minimum target
                exit_price = min_target
                method = "MIN_TARGET"
            
            exit_action = 'SELL'
            tag = 'MM_EXIT_GUARD_SELL'
            
        else:
            # BUY to take profit on short
            max_target = fill.fill_price - MIN_PROFIT_CENTS
            
            if bid > 0 and (fill.fill_price - bid) >= MIN_PROFIT_CENTS:
                # L1 bid is already at/below target
                exit_price = round(bid + spread * 0.15, 2)
                if exit_price > max_target:
                    exit_price = max_target
                method = "L1_BID"
            else:
                exit_price = max_target
                method = "MIN_TARGET"
            
            exit_action = 'BUY'
            tag = 'MM_EXIT_GUARD_BUY'
        
        profit_cents = abs(exit_price - fill.fill_price) * 100
        
        return {
            'symbol': symbol,
            'action': exit_action,
            'qty': fill.fill_qty,
            'price': round(exit_price, 2),
            'hidden': True,
            'tag': tag,
            'order_type': 'LIMIT',
            'method': method,
            'fill_price': fill.fill_price,
            'profit_target_cents': round(profit_cents, 1),
            'account_id': fill.account_id,
            'guard_source': 'MM_EXIT_GUARD',
            'fill_action': fill.action,
            'fill_qty': fill.fill_qty,
            'fill_age_seconds': fill.age_seconds,
        }
    
    # =====================================================================
    # DATA HELPERS — per-account lookups
    # =====================================================================
    
    async def _get_open_orders(self, account_id: str) -> List[Dict]:
        """Fetch open orders from Redis or broker — ACCOUNT-SCOPED."""
        try:
            redis = self._get_redis()
            if not redis:
                return []
            
            # Try Redis cache first (set by order manager) — per-account key
            key = f"psfalgo:open_orders:{account_id}"
            raw = redis.get(key)
            if raw:
                data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    # Wrapped format: {orders: [...], _meta: {...}}
                    orders = data.get('orders', [])
                    if isinstance(orders, list):
                        return orders
                    return list(data.values()) if data else []
            
            # Fallback: try Hammer Pro Redis format
            key2 = f"hammer:open_orders:{account_id}"
            raw2 = redis.get(key2)
            if raw2:
                data2 = json.loads(raw2.decode() if isinstance(raw2, bytes) else raw2)
                return data2 if isinstance(data2, list) else []
            
            # Fallback 2: try via position snapshot API
            try:
                from app.psfalgo.position_snapshot_api import get_position_snapshot_api
                pos_api = get_position_snapshot_api()
                if pos_api and hasattr(pos_api, 'get_open_orders'):
                    orders = await pos_api.get_open_orders(account_id=account_id)
                    if orders:
                        return [
                            {
                                'symbol': getattr(o, 'symbol', ''),
                                'action': getattr(o, 'action', ''),
                                'price': float(getattr(o, 'price', 0)),
                                'qty': float(getattr(o, 'total_qty', getattr(o, 'qty', 0))),
                                'status': getattr(o, 'status', 'UNKNOWN'),
                                'tag': getattr(o, 'tag', getattr(o, 'tif', '')),
                            }
                            for o in orders
                        ]
            except Exception:
                pass
            
            return []
            
        except Exception as e:
            logger.debug(f"[MM_EXIT_GUARD] Open orders fetch error for {account_id}: {e}")
            return []
    
    async def _get_l1_data(self, symbol: str) -> Dict:
        """Get L1 bid/ask data from Redis."""
        try:
            redis = self._get_redis()
            if not redis:
                return {}
            
            # Try L1 cache
            key = f"l1:{symbol}"
            raw = redis.get(key)
            if raw:
                data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                return data
            
            # Try truth ticks inspect (has bid/ask)
            key2 = f"truth_ticks:inspect:{symbol}"
            raw2 = redis.get(key2)
            if raw2:
                data2 = json.loads(raw2.decode() if isinstance(raw2, bytes) else raw2)
                inner = data2.get('data', {})
                return {
                    'bid': inner.get('bid', 0),
                    'ask': inner.get('ask', 0),
                }
            
            return {}
            
        except Exception as e:
            logger.debug(f"[MM_EXIT_GUARD] L1 data error for {symbol}: {e}")
            return {}
    
    # =====================================================================
    # PERIODIC CHECK LOOP
    # =====================================================================
    
    async def start_periodic_check(self):
        """Start periodic guard check loop."""
        self._running = True
        self._load_from_redis()
        
        logger.info(
            f"[MM_EXIT_GUARD] 🛡️ Starting periodic check (every {GUARD_CHECK_INTERVAL}s) "
            f"| {len(self._tracked)} fills being tracked across all accounts"
        )
        
        while self._running:
            try:
                await asyncio.sleep(GUARD_CHECK_INTERVAL)
                
                if not self._tracked:
                    continue
                
                orders_needed = await self.check_all_fills()
                
                if orders_needed:
                    for order in orders_needed:
                        await self._place_exit_order(order)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MM_EXIT_GUARD] Periodic check error: {e}")
    
    def stop(self):
        """Stop periodic check."""
        self._running = False
        logger.info("[MM_EXIT_GUARD] Stopped")
    
    # =====================================================================
    # ORDER PLACEMENT
    # =====================================================================
    
    async def _place_exit_order(self, order: Dict[str, Any]) -> bool:
        """
        Place the exit order via the order pipeline.
        ACCOUNT-SCOPED: order is placed in the account specified in the order dict.
        """
        symbol = order['symbol']
        account_id = order['account_id']
        
        try:
            # Try via order manager (direct placement)
            from app.psfalgo.order_manager import get_order_controller
            oc = get_order_controller()
            
            if oc:
                result = await oc.send_order(
                    account_id=account_id,
                    symbol=symbol,
                    action=order['action'],
                    qty=int(order['qty']),
                    price=order['price'],
                    order_type='LIMIT',
                    hidden=True,
                    tag=order['tag'],
                    source='MM_EXIT_GUARD',
                )
                
                if result and result.get('success'):
                    self.on_exit_confirmed(symbol, account_id)
                    # Update tracked fill with exit price
                    key = _tracking_key(account_id, symbol)
                    if key in self._tracked:
                        self._tracked[key].exit_order_price = order['price']
                        self._save_to_redis()
                    
                    logger.warning(
                        f"[MM_EXIT_GUARD] ✅ [{account_id}] EXIT ORDER PLACED: "
                        f"{order['action']} {order['qty']}lot {symbol} "
                        f"@${order['price']:.2f} HIDDEN LIMIT | "
                        f"fill was {order['fill_action']} @${order['fill_price']:.2f} | "
                        f"target profit: +{order['profit_target_cents']:.0f}c | "
                        f"method={order['method']} | tag={order['tag']}"
                    )
                    return True
                else:
                    logger.error(
                        f"[MM_EXIT_GUARD] ❌ [{account_id}] EXIT ORDER FAILED: {symbol} "
                        f"{order['action']} @${order['price']:.2f} — "
                        f"result={result}"
                    )
                    return False
            else:
                logger.error("[MM_EXIT_GUARD] OrderController not available")
                return False
                
        except Exception as e:
            logger.error(f"[MM_EXIT_GUARD] Order placement error for {account_id}:{symbol}: {e}")
            return False
    
    # =====================================================================
    # STATUS / DIAGNOSTICS — per-account breakdown
    # =====================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get guard status for dashboard/API — with per-account breakdown."""
        all_fills = []
        for f in self._tracked.values():
            all_fills.append({
                'symbol': f.symbol,
                'action': f.action,
                'fill_price': f.fill_price,
                'fill_qty': f.fill_qty,
                'age_min': round(f.age_seconds / 60, 1),
                'exit_needed': f.required_exit_action,
                'min_exit_price': f.min_exit_price,
                'exit_placed': f.exit_order_placed,
                'exit_price': f.exit_order_price,
                'checks': f.guard_check_count,
                'account': f.account_id,
            })
        
        unguarded = [a for a in all_fills if not a['exit_placed']]
        
        # Per-account breakdown
        by_account: Dict[str, Dict[str, Any]] = {}
        for f in all_fills:
            acct = f['account']
            if acct not in by_account:
                by_account[acct] = {'total': 0, 'unguarded': 0, 'guarded': 0, 'symbols': []}
            by_account[acct]['total'] += 1
            by_account[acct]['symbols'].append(f['symbol'])
            if f['exit_placed']:
                by_account[acct]['guarded'] += 1
            else:
                by_account[acct]['unguarded'] += 1
        
        return {
            'engine': 'MM_EXIT_GUARD',
            'total_tracked': len(self._tracked),
            'unguarded_count': len(unguarded),
            'guarded_count': len(all_fills) - len(unguarded),
            'check_interval_sec': GUARD_CHECK_INTERVAL,
            'min_profit_cents': MIN_PROFIT_CENTS * 100,
            'min_fill_lot': MIN_FILL_LOT,
            'per_account': by_account,
            'tracked_fills': all_fills,
            'unguarded_fills': unguarded,
        }
    
    def get_fills_for_account(self, account_id: str) -> List[Dict[str, Any]]:
        """Get tracked fills for a specific account."""
        return [
            f.to_dict() for f in self._tracked.values()
            if f.account_id == account_id
        ]


# ============================================================================
# GLOBAL SINGLETON
# ============================================================================

_guard_instance: Optional[MMExitGuard] = None


def get_mm_exit_guard() -> MMExitGuard:
    """Get global MMExitGuard instance."""
    global _guard_instance
    if _guard_instance is None:
        _guard_instance = MMExitGuard()
    return _guard_instance


def initialize_mm_exit_guard() -> MMExitGuard:
    """Initialize (or re-initialize) global MMExitGuard."""
    global _guard_instance
    _guard_instance = MMExitGuard()
    return _guard_instance
