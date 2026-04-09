"""
Dual Account REV Service

Dual Process sürecinde her iki hesabı da (HAMPRO, IBKR_PED) ayrı ayrı kontrol eder
ve REV order'ları Redis'e yazar. XNL Engine bu order'ları okuyup gönderir.

Redis Keys:
- psfalgo:rev_queue:HAMPRO → List of pending REV orders for HAMPRO
- psfalgo:rev_queue:IBKR_PED → List of pending REV orders for IBKR_PED

Her REV order JSON formatında:
{
    "symbol": "CIM PRD",
    "action": "BUY",
    "qty": 200,
    "price": 23.45,
    "tag": "REV_IBKR_PED_LT_LONG_DEC",
    "account_id": "IBKR_PED",
    "created_at": "2026-02-06T20:30:00",
    "source": "dual_account_rev_service"
}
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, List, Any, Optional
from loguru import logger


# REV order'lar bu key'lerde tutulur
REV_QUEUE_KEY_TEMPLATE = "psfalgo:rev_queue:{account_id}"
# REV queue TTL (24 saat - gün sonunda temizlenir)
REV_QUEUE_TTL_SECONDS = 24 * 60 * 60


class DualAccountRevService:
    """
    Dual Process için her iki hesabı da kontrol edip REV order'ları Redis'e yazar.
    XNL Engine bu order'ları okuyup gönderir.
    """
    
    def __init__(self, redis_client=None):
        self.redis_client = redis_client
        self.running = False
        self._init_redis()
        
        # RevOrderEngine for calculating REV prices
        from app.terminals.revorder_config import load_revorder_config
        from app.terminals.revorder_engine import RevOrderEngine
        self.config = load_revorder_config()
        self.rev_engine = RevOrderEngine(self.config)
        
        logger.info("[DualAccountRevService] Initialized")
    
    def _init_redis(self):
        """Initialize Redis client"""
        if self.redis_client:
            return
        try:
            from app.core.redis_client import get_redis_client
            self.redis_client = get_redis_client()
        except Exception as e:
            logger.error(f"[DualAccountRevService] Redis init error: {e}")
    
    async def check_account_health(self, account_id: str) -> List[Dict[str, Any]]:
        """
        Health check with anti-reversal protection.
        MARKET HOURS ONLY: 9:30-16:00 US Eastern Time.
        
        V3 DESIGN:
        ═══════════════════════════════════════════════════════════════
        1. Gap = befday - current (NOT potential!)
        2. abs(gap) >= 200 → REV needed
        3. Anti-reversal: REV + existing same-side orders must NOT cross 0
           - Long (current>0) → total SELL orders must not exceed current
           - Short (current<0) → total BUY orders must not exceed abs(current)
        4. Source-specific thresholds:
           - TP (POS INC): $0.05
           - RL (POS DEC): LT/KB $0.08, MM $0.13
        ═══════════════════════════════════════════════════════════════
        """
        rev_orders = []
        
        try:
            # ── MARKET HOURS GUARD ──
            try:
                from zoneinfo import ZoneInfo
                _et_now = datetime.now(ZoneInfo('America/New_York'))
                _time_val = _et_now.hour * 100 + _et_now.minute
                if not (930 <= _time_val < 1600):
                    logger.debug(f"[REV] Outside US market hours (9:30-16:00 ET). Skipping {account_id}.")
                    return []
            except Exception:
                pass  # Fail open if timezone handling fails
            
            # 1. Get position snapshots
            snapshots = await self._fetch_snapshots(account_id)
            if not snapshots:
                logger.debug(f"[REV] No snapshots for {account_id}")
                return []
            
            logger.info(f"[REV] Checking {len(snapshots)} positions for {account_id}")
            
            # 2. Pre-fetch open orders (WITH direction and qty) for anti-reversal
            open_orders_by_symbol = self._get_open_orders_by_symbol(account_id)
            already_queued = self._get_queued_symbols(account_id)
            
            checked = 0
            skipped_healthy = 0
            skipped_antireversal = 0
            skipped_queued = 0
            
            # 3. Check each position
            for snap in snapshots:
                symbol = getattr(snap, 'symbol', '')
                befday = float(getattr(snap, 'befday_qty', 0) or 0)
                current = float(getattr(snap, 'qty', 0) or 0)
                potential = float(getattr(snap, 'potential_qty', 0) or 0)
                
                # Skip if both zero (untouched, no position)
                if abs(befday) < 0.01 and abs(current) < 0.01:
                    continue
                
                # ── STEP 1: REV eligibility check ──
                # REV should ONLY fire when befday differs from BOTH current AND potential.
                # ═══════════════════════════════════════════════════════════════
                # befday ≈ current  → No fills happened yet → No REV needed
                # befday ≈ potential → Open orders will bring position back → No REV needed
                # befday ≠ current AND befday ≠ potential → Fill happened AND
                #   open orders won't correct it → REV IS needed
                # ═══════════════════════════════════════════════════════════════
                current_gap = befday - current
                potential_gap = befday - potential
                
                # If befday ≈ current → no fill happened, nothing to reverse
                if abs(current_gap) < 200:
                    skipped_healthy += 1
                    continue
                
                # If befday ≈ potential → open orders already correct the deviation
                if abs(potential_gap) < 200:
                    skipped_healthy += 1
                    continue
                
                # Both gaps are significant → fill happened AND no open orders fix it
                effective_gap = potential_gap
                
                # ── STEP 2: Reverse position check ──
                # Position should never cross sides (long → short or short → long)
                if befday < -0.01 and current > 0.01:
                    logger.error(
                        f"[REV] ⛔ REVERSE DETECTED {symbol} ({account_id}): "
                        f"Befday={befday:.0f} (short) but Current={current:.0f} (long)!"
                    )
                    continue
                if befday > 0.01 and current < -0.01:
                    logger.error(
                        f"[REV] ⛔ REVERSE DETECTED {symbol} ({account_id}): "
                        f"Befday={befday:.0f} (long) but Current={current:.0f} (short)!"
                    )
                    continue
                
                # ── STEP 3: Check if NEWC-sourced (skip — NEWC manages own TP) ──
                source = self._detect_source(symbol, account_id)
                if source == 'NEWC':
                    logger.debug(
                        f"[REV] {symbol}: NEWC-sourced gap, skipping "
                        f"(NEWCLMM manages own profit-taking)"
                    )
                    continue
                
                # ── STEP 4: Determine REV type and direction ──
                pos_change = 'POS_INC' if abs(current) > abs(befday) else 'POS_DEC'
                
                # REV direction: which way do we need to push to reach befday?
                # effective_gap > 0 → need to BUY (position is below befday)
                # effective_gap < 0 → need to SELL (position is above befday)
                rev_action = 'BUY' if effective_gap > 0 else 'SELL'
                rev_type = 'TP' if pos_change == 'POS_INC' else 'RL'
                
                # ── STEP 4: Anti-reversal — never cross befday to opposite side ──
                # Calculate how much we can safely send without pushing past befday
                symbol_orders = open_orders_by_symbol.get(symbol, [])
                
                if rev_action == 'SELL':
                    existing_sell_qty = sum(
                        float(o.get('qty', 0))
                        for o in symbol_orders
                        if o.get('action', '').upper() in ('SELL', 'SHORT', 'SSHORT')
                    )
                    # Max SELL = current position (can't sell more than we have → no reversal)
                    # But also account for existing sell orders
                    max_safe_sell = max(0, abs(current) - existing_sell_qty)
                    rev_qty = min(abs(effective_gap), max_safe_sell)
                    
                    if max_safe_sell < 200:
                        skipped_antireversal += 1
                        logger.debug(
                            f"[REV] ⏩ {symbol}: max_safe_sell={max_safe_sell:.0f} < 200 "
                            f"(current={current:.0f}, existing_sell={existing_sell_qty:.0f})"
                        )
                        continue
                else:  # BUY
                    existing_buy_qty = sum(
                        float(o.get('qty', 0))
                        for o in symbol_orders
                        if o.get('action', '').upper() in ('BUY', 'COVER')
                    )
                    # Max BUY = abs(current) for short positions (can't buy more than shorted)
                    max_safe_buy = max(0, abs(current) - existing_buy_qty)
                    rev_qty = min(abs(effective_gap), max_safe_buy)
                    
                    if max_safe_buy < 200:
                        skipped_antireversal += 1
                        logger.debug(
                            f"[REV] ⏩ {symbol}: max_safe_buy={max_safe_buy:.0f} < 200 "
                            f"(current={current:.0f}, existing_buy={existing_buy_qty:.0f})"
                        )
                        continue
                
                # Final check: REV qty must be at least 200
                if rev_qty < 200:
                    skipped_antireversal += 1
                    continue
                
                # ── STEP 5: Queue check ──
                if symbol in already_queued:
                    skipped_queued += 1
                    continue
                
                checked += 1
                
                logger.info(
                    f"[REV] 📊 {symbol}: befday={befday:.0f} current={current:.0f} "
                    f"potential={potential:.0f} → gap={effective_gap:.0f} → "
                    f"{rev_type} {rev_action} {rev_qty:.0f} lot"
                )
                
                # ── STEP 6: Calculate REV order (price, source, tag) ──
                rev_order = await self._calculate_rev_order_v3(
                    snap, rev_action, rev_type, rev_qty, effective_gap, account_id
                )
                if rev_order:
                    rev_orders.append(rev_order)
            
            logger.info(
                f"[REV] {account_id} summary: checked={checked}, "
                f"rev_generated={len(rev_orders)}, "
                f"skipped_healthy={skipped_healthy}, "
                f"skipped_antireversal={skipped_antireversal}, "
                f"skipped_queued={skipped_queued}"
            )
            
            return rev_orders
            
        except Exception as e:
            logger.error(f"[REV] Error checking {account_id}: {e}", exc_info=True)
            return []
    
    def _get_open_orders_by_symbol(self, account_id: str) -> Dict[str, List[Dict]]:
        """
        Get ALL open orders grouped by symbol with action and qty.
        Used for anti-reversal calculation.
        
        Returns: {symbol: [{action, qty, price, tag}, ...]}
        """
        from collections import defaultdict
        result = defaultdict(list)
        
        try:
            if not self.redis_client:
                return result
            
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            raw = redis_sync.get(f"psfalgo:open_orders:{account_id}")
            if not raw:
                return result
            
            data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            orders = data if isinstance(data, list) else data.get('orders', [])
            
            for order in orders:
                if not isinstance(order, dict):
                    continue
                sym = order.get('symbol', '')
                if sym:
                    result[sym].append({
                        'action': order.get('action', ''),
                        'qty': float(order.get('qty', 0) or order.get('totalQuantity', 0) or 0),
                        'price': float(order.get('price', 0) or order.get('lmtPrice', 0) or 0),
                        'tag': order.get('tag', '') or order.get('strategy_tag', '') or order.get('orderRef', ''),
                    })
            
            return result
        except Exception as e:
            logger.debug(f"[REV] Open orders fetch error: {e}")
            return result
    
    def _detect_source(self, symbol: str, account_id: str) -> str:
        """
        Detect the SOURCE engine from the most recent fill tag for this symbol.
        
        CRITICAL FIX: Matches both Hammer format (BML-H) and display format (BML PRH).
        
        Returns: 'LT', 'MM', 'KB', 'PA', 'AN'
        """
        # Build symbol variants for matching
        try:
            from app.live.symbol_mapper import SymbolMapper
            hammer_sym = SymbolMapper.to_hammer_symbol(symbol)
            display_sym = SymbolMapper.to_display_symbol(symbol)
            symbol_variants = {symbol, hammer_sym, display_sym}
        except Exception:
            symbol_variants = {symbol}
        
        try:
            # Check Redis fill stream — only today's market hours fills
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            try:
                from zoneinfo import ZoneInfo
                _et_now = datetime.now(ZoneInfo('America/New_York'))
                _mkt_open = _et_now.replace(hour=9, minute=30, second=0, microsecond=0)
                _min_id = f"{int(_mkt_open.timestamp() * 1000)}-0"
            except Exception:
                _min_id = '-'
            entries = redis_sync.xrevrange("psfalgo:execution:ledger", max='+', min=_min_id, count=500)
            
            if entries:
                for entry_id, data in entries:
                    decoded = {
                        (k.decode() if isinstance(k, bytes) else k):
                        (v.decode() if isinstance(v, bytes) else v)
                        for k, v in data.items()
                    }
                    # Match symbol against both fields
                    entry_symbol = decoded.get('symbol', '')
                    entry_display = decoded.get('display_symbol', '')
                    if entry_symbol not in symbol_variants and entry_display not in symbol_variants:
                        continue
                    
                    # Account isolation: only use fills from THIS account
                    fill_acct = (decoded.get('account_id', '') or '').upper()
                    acct_upper = account_id.upper()
                    if not (fill_acct == acct_upper
                            or (acct_upper in ('HAMPRO', 'HAMMER_PRO') and fill_acct in ('HAMPRO', 'HAMMER_PRO'))
                            or (acct_upper.startswith('IBKR') and fill_acct.startswith('IBKR'))):
                        continue
                    
                    # Use the 'tag' field first (more specific), then fall back to order_id
                    tag = (decoded.get('tag', '') or decoded.get('order_id', '') or '').upper()
                    clean = tag.replace('FR_', '').replace('REV_TP_', '').replace('REV_RL_', '').replace('OZEL_', '')
                    # v4 dual-tag: first part is POS (MM/LT), second is ENGINE
                    parts = clean.split('_')
                    if len(parts) >= 2:
                        engine_part = parts[1]  # Second part in MM_MM_... or LT_PA_...
                        if engine_part in ('PA', 'AN', 'KB', 'TRIM', 'MM', 'NEWC'):
                            return engine_part
                    # NEWC tag detection (MM_NEWC_LONG_INC etc)
                    if 'NEWC' in clean:
                        return 'NEWC'
                    # Legacy tag format fallback
                    if clean.startswith('LT_') or 'TRIM' in clean:
                        return 'TRIM'
                    if clean.startswith('KARBOTU') or clean.startswith('HEAVY'):
                        return 'KB'
                    if clean.startswith('MM_'):
                        return 'MM'
                    if clean.startswith('PATADD') or clean.startswith('PAT'):
                        return 'PA'
                    if clean.startswith('ADDNEWPOS'):
                        return 'AN'
                    return 'MM'  # Default if tag doesn't match
        except Exception:
            pass
        
        return 'MM'  # Default source
    
    async def _calculate_rev_order_v3(
        self, snap, rev_action: str, rev_type: str, rev_qty: float,
        gap: float, account_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate REV order with v4 dual-tag format and source-specific thresholds.
        
        Tag Format: REV_{TP/RL}_{POS}_{ENGINE}_{BUY/SELL}
        POS: MM or LT (from position)
        ENGINE: MM, PA, AN, KB, TRIM
        Pricing: RevOrderEngine 2-phase (L1 → Orderbook)
        Threshold: POS=MM → TP=$0.05/RL=$0.13, POS=LT → TP=$0.09/RL=$0.08
        """
        try:
            symbol = getattr(snap, 'symbol', '')
            befday = float(getattr(snap, 'befday_qty', 0) or 0)
            current = float(getattr(snap, 'qty', 0) or 0)
            current_price = float(getattr(snap, 'current_price', 0) or 0)
            
            # ── Source detection from fill tag ──
            source = self._detect_source(symbol, account_id)
            
            # ── POS TAG: look up from position data ──
            pos_tag = "MM"  # Default
            try:
                import json
                redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
                # 🔑 ACCOUNT ISOLATION: Use per-account POS TAG key
                raw = redis_sync.get(f"psfalgo:pos_tags:{account_id}")
                if not raw:
                    # Fallback: legacy global key (migration only)
                    raw = redis_sync.get("psfalgo:pos_tags")
                if raw:
                    tags = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                    pos_tag = tags.get(symbol, 'MM')
            except Exception:
                pass
            
            # ── Build fill tag for RevOrderEngine (dual-tag v4 format) ──
            is_long = current > 0 or (abs(current) < 0.01 and befday > 0)
            pos_change = 'INC' if rev_type == 'TP' else 'DEC'
            direction = 'LONG' if is_long else 'SHORT'
            
            # Tag in v4 format: {POS}_{ENGINE}_{DIR}_{ACTION}
            tag_type = f"{pos_tag}_{source}_{direction}_{pos_change}"
            
            # ── Fill action (opposite of REV) ──
            fill_action = 'SELL' if rev_action == 'BUY' else 'BUY'
            
            # ── Fill price lookup ──
            fill_price = await self._lookup_fill_price(symbol, fill_action, account_id)
            
            if not fill_price and current_price > 0:
                fill_price = current_price
                logger.info(f"[REV] {symbol} Using current_price as fallback: ${fill_price:.2f}")
            
            if not fill_price or fill_price <= 0:
                logger.warning(f"[REV] No price data for {symbol}, cannot calculate REV")
                return None
            
            # ── Build pseudo-fill for RevOrderEngine ──
            pseudo_fill = {
                'symbol': symbol,
                'action': fill_action,
                'qty': rev_qty,
                'price': fill_price,
                'tag': tag_type,
                'account_id': account_id,
                'order_id': f"dual_rev_{symbol}_{int(datetime.now().timestamp())}"
            }
            
            # Get L1 data for orderbook pricing
            l1_data = await self._get_l1_data(symbol)
            
            # Use RevOrderEngine for 2-phase pricing
            rev_order = self.rev_engine.calculate_rev_order(pseudo_fill, l1_data)
            
            if not rev_order:
                logger.warning(f"[REV] RevOrderEngine returned None for {symbol}")
                return None
            
            # Override qty with anti-reversal-safe qty
            rev_order['qty'] = rev_qty
            
            logger.info(
                f"[REV] ✅ {rev_order['tag']} {rev_action} {rev_qty:.0f} {symbol} "
                f"@${rev_order['price']:.2f} | Befday={befday:.0f} Current={current:.0f} "
                f"Gap={gap:.0f} | Source={source} Method={rev_order.get('method','')}"
            )
            
            return {
                "symbol": rev_order['symbol'],
                "action": rev_order['action'],
                "qty": rev_qty,
                "price": rev_order['price'],
                "tag": rev_order['tag'],
                "hidden": rev_order.get('hidden', True),
                "account_id": account_id,
                "created_at": datetime.now().isoformat(),
                "source": "dual_account_rev_service",
                "gap": gap,
                "rev_type": rev_order.get('rev_type', rev_type),
                "method": rev_order.get('method', ''),
                "source_engine": source,
                "befday": befday,
                "current": current,
                "_fill_price": fill_price,  # Actual fill cost for profit guard
            }
            
        except Exception as e:
            logger.error(f"[REV] REV calculation error for {getattr(snap, 'symbol', '?')}: {e}", exc_info=True)
            return None
    
    async def _fetch_snapshots(self, account_id: str):
        """Fetch position snapshots for account.
        
        CRITICAL: In Dual Process mode, backend's active account may differ from
        the account we're checking. Redis is the reliable source for BOTH accounts
        since PositionSnapshotAPI writes to psfalgo:positions:{account_id} per account.
        
        Priority:
        1. Redis (fast, always has both accounts' data, no context-switch needed)
        2. Backend API (fallback, may not have correct account context)
        """
        from types import SimpleNamespace
        
        # ═══════════════════════════════════════════════════════════════
        # SOURCE 1: Redis (PREFERRED for Dual Process — always up-to-date for both accounts)
        # ═══════════════════════════════════════════════════════════════
        try:
            if self.redis_client and getattr(self.redis_client, 'sync', None):
                positions_key = f"psfalgo:positions:{account_id}"
                raw_positions = self.redis_client.sync.get(positions_key)
                if raw_positions:
                    positions_dict = json.loads(raw_positions.decode() if isinstance(raw_positions, bytes) else raw_positions)
                    if positions_dict:
                        # CRITICAL: Check staleness — if Redis data is too old, 
                        # positions may have changed (fills happened but Redis wasn't updated)
                        import time as _time
                        meta = positions_dict.get('_meta', {})
                        updated_at = meta.get('updated_at', 0)
                        age_seconds = _time.time() - updated_at if updated_at else float('inf')
                        max_age = 300  # 5 minutes max staleness
                        
                        if age_seconds > max_age:
                            logger.warning(
                                f"[DualAccountRevService] ⚠️ Redis positions for {account_id} "
                                f"are stale ({age_seconds:.0f}s old > {max_age}s). "
                                f"Will try backend API for fresh data."
                            )
                            # Don't return — fall through to backend API
                        else:
                            out = []
                            for sym, pos_data in positions_dict.items():
                                if not sym or sym == '_meta':
                                    continue
                                out.append(SimpleNamespace(
                                    symbol=sym,
                                    befday_qty=float(pos_data.get('befday_qty', 0) or 0),
                                    potential_qty=float(pos_data.get('potential_qty', 0) or 0),
                                    qty=float(pos_data.get('qty', 0) or 0),
                                    current_price=float(pos_data.get('current_price', 0) or 0) if pos_data.get('current_price') else None,
                                ))
                            if out:
                                logger.info(f"[DualAccountRevService] ✅ Read {len(out)} positions from Redis for {account_id} (age={age_seconds:.0f}s)")
                                return out
        except Exception as redis_err:
            logger.debug(f"[DualAccountRevService] Redis read for {account_id}: {redis_err}")
        
        # ═══════════════════════════════════════════════════════════════
        # SOURCE 2: Backend API (fallback — may have stale context in dual mode)
        # ═══════════════════════════════════════════════════════════════
        import requests
        
        def _get():
            url = "http://localhost:8000/api/trading/positions"
            r = requests.get(url, params={"account_id": account_id}, timeout=10)
            r.raise_for_status()
            return r.json()
        
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, _get)
            positions = data.get("positions") or []
            
            out = []
            for p in positions:
                out.append(SimpleNamespace(
                    symbol=p.get("symbol", ""),
                    befday_qty=float(p.get("befday_qty") or 0),
                    potential_qty=float(p.get("potential_qty") or 0),
                    qty=float(p.get("qty") or p.get("quantity") or 0),
                    current_price=float(p.get("current_price") or 0),
                ))
            if out:
                return out
        except Exception as e:
            logger.warning(f"[DualAccountRevService] Backend fetch also failed for {account_id}: {e}")
        
        return []
    
    async def _calculate_rev_order(self, snap, gap: float, account_id: str) -> Optional[Dict[str, Any]]:
        """
        Calculate REV order from health gap using RevOrderEngine for proper
        orderbook-based pricing and correct tag format.
        
        Tag Format: REV_{SOURCE}_{DIRECTION}_{ACTION}
        - SOURCE: MM or LT (from original fill tag)
        - ACTION: INC or DEC (what the REV order does)
        """
        try:
            symbol = getattr(snap, 'symbol', '')
            befday = float(getattr(snap, 'befday_qty', 0) or 0)
            current = float(getattr(snap, 'qty', 0) or 0)
            current_price = float(getattr(snap, 'current_price', 0) or 0)
            
            qty = abs(gap)
            
            # Determine position direction and scenario
            is_long = befday > 0
            is_short = befday < 0
            
            # Determine tag_type (INC/DEC) for RevOrderEngine compatibility
            # INC = position increased beyond befday → TP needed
            # DEC = position decreased below befday → RELOAD needed
            if is_long:
                if current > befday:
                    tag_type = "MM_LONG_INC"   # Long Increase → SELL TP
                else:
                    tag_type = "MM_LONG_DEC"   # Long Decrease → BUY RELOAD
            elif is_short:
                if current < befday:
                    tag_type = "MM_SHORT_INC"  # Short Increase → BUY TP
                else:
                    tag_type = "MM_SHORT_DEC"  # Short Decrease → SELL RELOAD
            else:
                tag_type = "MM_LONG_INC"  # Fallback
            
            # Ensure tag has engine source prefix for RevOrderEngine
            # DualAccountRevService = health gap recovery → default MM source
            if not tag_type.startswith(('MM_', 'LT_')):
                tag_type = f"MM_{tag_type}"
            
            # Build pseudo-fill for RevOrderEngine
            # The fill action is the OPPOSITE of the REV action
            # gap > 0: need BUY to restore → original fill was SELL
            # gap < 0: need SELL to restore → original fill was BUY
            fill_action = 'SELL' if gap > 0 else 'BUY'
            
            # ═══════════════════════════════════════════════════════════════
            # FILL PRICE LOOKUP — Find actual fill price that caused the gap
            # Same multi-source strategy as RevRecoveryService
            # ═══════════════════════════════════════════════════════════════
            fill_price = await self._lookup_fill_price(symbol, fill_action, account_id)
            
            if not fill_price and current_price > 0:
                fill_price = current_price
                logger.info(
                    f"[DualAccountRevService] {symbol} Using current_price "
                    f"as fallback: ${fill_price:.2f}"
                )
            
            if not fill_price or fill_price <= 0:
                logger.warning(f"[DualAccountRevService] No price data for {symbol}, cannot calculate REV")
                return None
            
            pseudo_fill = {
                'symbol': symbol,
                'action': fill_action,
                'qty': qty,
                'price': fill_price,
                'tag': tag_type,
                'account_id': account_id,
                'order_id': f"dual_rev_{symbol}_{int(datetime.now().timestamp())}"
            }
            
            # Get L1 data for orderbook pricing
            l1_data = await self._get_l1_data(symbol)
            
            # Use RevOrderEngine for proper orderbook-based pricing
            rev_order = self.rev_engine.calculate_rev_order(pseudo_fill, l1_data)
            
            if not rev_order:
                logger.warning(f"[DualAccountRevService] RevOrderEngine returned None for {symbol}")
                return None
            
            return {
                "symbol": rev_order['symbol'],
                "action": rev_order['action'],
                "qty": rev_order['qty'],
                "price": rev_order['price'],
                "tag": rev_order['tag'],
                "hidden": rev_order.get('hidden', True),
                "account_id": account_id,
                "created_at": datetime.now().isoformat(),
                "source": "dual_account_rev_service",
                "gap": gap,
                "rev_type": rev_order.get('rev_type', ''),
                "method": rev_order.get('method', ''),
            }
            
        except Exception as e:
            logger.error(f"[DualAccountRevService] REV calculation error: {e}", exc_info=True)
            return None
    
    async def _lookup_fill_price(self, symbol: str, required_action: str, account_id: str) -> Optional[float]:
        """
        Look up fill price from Redis stream and CSV files.
        Same multi-source strategy as RevRecoveryService._get_last_fill_price.
        
        CRITICAL FIX: Matches both Hammer format (BML-H) and display format (BML PRH)
        because the ledger may store symbols in either format depending on the source
        (Hammer fills listener uses Hammer format, IBKR connector uses display format).
        
        Args:
            symbol: Stock symbol (display format, e.g. "BML PRH")
            required_action: 'BUY' or 'SELL' — the action that caused the gap
            account_id: Account to search fills for
        
        Returns:
            Fill price or None
        """
        # Build set of symbol variants to match against
        try:
            from app.live.symbol_mapper import SymbolMapper
            hammer_sym = SymbolMapper.to_hammer_symbol(symbol)
            display_sym = SymbolMapper.to_display_symbol(symbol)
            symbol_variants = {symbol, hammer_sym, display_sym}
        except Exception:
            symbol_variants = {symbol}
        
        # SOURCE 1: Redis Stream — only today's market hours fills (9:30-16:00 ET)
        try:
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            try:
                from zoneinfo import ZoneInfo
                _et_now = datetime.now(ZoneInfo('America/New_York'))
                _mkt_open = _et_now.replace(hour=9, minute=30, second=0, microsecond=0)
                _min_id = f"{int(_mkt_open.timestamp() * 1000)}-0"
            except Exception:
                _min_id = '-'
            entries = redis_sync.xrevrange("psfalgo:execution:ledger", max='+', min=_min_id, count=500)
            
            if entries:
                for entry_id, data in entries:
                    decoded = {
                        (k.decode() if isinstance(k, bytes) else k):
                        (v.decode() if isinstance(v, bytes) else v)
                        for k, v in data.items()
                    }
                    # Match symbol against BOTH 'symbol' AND 'display_symbol' fields
                    entry_symbol = decoded.get('symbol', '')
                    entry_display = decoded.get('display_symbol', '')
                    symbol_match = (
                        entry_symbol in symbol_variants 
                        or entry_display in symbol_variants
                    )
                    if not symbol_match:
                        continue
                    
                    # Account isolation: only use fills from THIS account
                    fill_acct = (decoded.get('account_id', '') or '').upper()
                    acct_upper = account_id.upper()
                    acct_match = (
                        fill_acct == acct_upper
                        or (acct_upper in ('HAMPRO', 'HAMMER_PRO') and fill_acct in ('HAMPRO', 'HAMMER_PRO'))
                        or (acct_upper.startswith('IBKR') and fill_acct.startswith('IBKR'))
                    )
                    if not acct_match:
                        continue
                    action = decoded.get('action', decoded.get('side', '')).upper()
                    if action == required_action.upper():
                        price = float(decoded.get('price', 0))
                        if price > 0:
                            logger.info(
                                f"[DualAccountRevService] Fill lookup {symbol}: "
                                f"found {action} @ ${price:.2f} (Redis stream, "
                                f"matched via '{entry_symbol}'/'{entry_display}')"
                            )
                            return price
        except Exception as e:
            logger.debug(f"[DualAccountRevService] Redis stream query for {symbol}: {e}")
        
        # SOURCE 2: CSV Files (persistent)
        try:
            from app.trading.daily_fills_store import get_daily_fills_store
            import os, csv
            
            fills_store = get_daily_fills_store()
            filename = fills_store._get_filename(account_id)
            filepath = os.path.join(fills_store.log_dir, filename)
            
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    rows = list(csv.DictReader(f))
                
                for row in reversed(rows):
                    if row.get("Symbol") == symbol:
                        action = row.get("Action", "").upper()
                        if action == required_action.upper():
                            price = float(row.get("Price", 0))
                            if price > 0:
                                logger.info(
                                    f"[DualAccountRevService] Fill lookup {symbol}: "
                                    f"found {action} @ ${price:.2f} (CSV)"
                                )
                                return price
        except Exception as e:
            logger.debug(f"[DualAccountRevService] CSV query for {symbol}: {e}")
        
        return None
    
    async def _get_l1_data(self, symbol: str) -> Dict[str, Any]:
        """Get L1 market data from Redis for orderbook pricing.
        
        🔑 TICKER CONVENTION: Tries both Hammer format (WBS-F) and PREF_IBKR
        format (WBS PRF) keys to ensure L1 data is found regardless of which
        format the caller passes.
        """
        try:
            if not self.redis_client:
                return {'bid': 0, 'ask': 0, 'spread': 0.02}
            
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            
            # Build list of symbol formats to try
            from app.live.symbol_mapper import SymbolMapper
            hammer_sym = SymbolMapper.to_hammer_symbol(symbol)
            display_sym = SymbolMapper.to_display_symbol(symbol)
            
            # Try all format variants (dedup)
            formats_to_try = list(dict.fromkeys([symbol, hammer_sym, display_sym]))
            
            for sym in formats_to_try:
                # Try market:l1:{sym}
                raw = redis_sync.get(f"market:l1:{sym}")
                if raw:
                    data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                    bid = float(data.get('bid', 0) or 0)
                    ask = float(data.get('ask', 0) or 0)
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        return {'bid': bid, 'ask': ask, 'spread': spread}
            
            # Fallback: try market_data:snapshot:{sym} with same format list
            for sym in formats_to_try:
                raw = redis_sync.get(f"market_data:snapshot:{sym}")
                if raw:
                    data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                    bid = float(data.get('bid', 0) or 0)
                    ask = float(data.get('ask', 0) or 0)
                    if bid > 0 and ask > 0:
                        spread = ask - bid
                        return {'bid': bid, 'ask': ask, 'spread': spread}
            
        except Exception as e:
            logger.debug(f"[DualAccountRevService] L1 fetch for {symbol}: {e}")
        
        return {'bid': 0, 'ask': 0, 'spread': 0.02}
    
    def queue_rev_orders(self, account_id: str, rev_orders: List[Dict[str, Any]]) -> int:
        """
        REV order'ları Redis queue'ya ekle.
        
        Returns:
            Number of orders queued
        """
        if not self.redis_client or not rev_orders:
            return 0
        
        try:
            key = REV_QUEUE_KEY_TEMPLATE.format(account_id=account_id)
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            
            count = 0
            for order in rev_orders:
                # Check if already queued (by symbol)
                existing = self._get_queued_symbols(account_id)
                if order['symbol'] in existing:
                    logger.debug(f"[DualAccountRevService] {order['symbol']} already queued for {account_id}")
                    continue
                
                # CRITICAL: Always stamp created_at so pop_rev_orders can filter stale orders
                if 'created_at' not in order or not order['created_at']:
                    order['created_at'] = datetime.now().isoformat()
                
                # Add to queue
                redis_sync.rpush(key, json.dumps(order))
                count += 1
                logger.info(
                    f"[DualAccountRevService] ✅ Queued REV: {order['action']} {order['qty']:.0f} {order['symbol']} "
                    f"@ ${order['price']:.2f} | Tag: {order['tag']} | Account: {account_id}"
                )
            
            # Set TTL
            if count > 0:
                redis_sync.expire(key, REV_QUEUE_TTL_SECONDS)
            
            return count
            
        except Exception as e:
            logger.error(f"[DualAccountRevService] Queue error: {e}")
            return 0
    
    def _get_queued_symbols(self, account_id: str) -> set:
        """Get symbols already in queue for account"""
        try:
            key = REV_QUEUE_KEY_TEMPLATE.format(account_id=account_id)
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            items = redis_sync.lrange(key, 0, -1)
            
            symbols = set()
            for item in items:
                try:
                    data = json.loads(item.decode() if isinstance(item, bytes) else item)
                    symbols.add(data.get('symbol', ''))
                except:
                    pass
            return symbols
        except:
            return set()
    
    def _get_open_order_symbols(self, account_id: str) -> set:
        """
        Get symbols that already have open orders for this account.
        Reads from psfalgo:open_orders:{account_id} Redis key.
        
        This prevents recalculating REV prices (and hitting getQuotes timeouts)
        for positions that already have orders in the market.
        """
        try:
            if not self.redis_client:
                return set()
            
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            raw = redis_sync.get(f"psfalgo:open_orders:{account_id}")
            if not raw:
                return set()
            
            data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            symbols = set()
            
            # Handle both list and dict formats
            orders = data if isinstance(data, list) else data.get('orders', [])
            for order in orders:
                sym = order.get('symbol', '') if isinstance(order, dict) else ''
                if sym:
                    symbols.add(sym)
            
            return symbols
        except Exception as e:
            logger.debug(f"[DualAccountRevService] Open orders check error: {e}")
            return set()
    
    def pop_rev_orders(self, account_id: str) -> List[Dict[str, Any]]:
        """
        Get and remove all REV orders from queue for account.
        
        CRITICAL: Only returns orders created TODAY during US market hours
        (9:00-16:00 ET). Stale orders from previous days are DROPPED.
        All orders are 1-day only — never carry over.
        
        Returns:
            List of valid (today-only) REV orders to execute
        """
        if not self.redis_client:
            return []
        
        try:
            key = REV_QUEUE_KEY_TEMPLATE.format(account_id=account_id)
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            
            # Get today's market open timestamp (9:00 ET) as cutoff
            try:
                from zoneinfo import ZoneInfo
                et_now = datetime.now(ZoneInfo('America/New_York'))
                today_market_open = et_now.replace(hour=9, minute=0, second=0, microsecond=0)
                cutoff_iso = today_market_open.isoformat()
            except Exception:
                cutoff_iso = None
            
            all_orders = []
            while True:
                item = redis_sync.lpop(key)
                if not item:
                    break
                try:
                    data = json.loads(item.decode() if isinstance(item, bytes) else item)
                    all_orders.append(data)
                except:
                    pass
            
            # Filter: only keep orders created TODAY (after 9:00 ET)
            # CRITICAL: Orders WITHOUT created_at are treated as STALE (drop them)
            valid_orders = []
            stale_count = 0
            no_timestamp_count = 0
            for order in all_orders:
                created_at = order.get('created_at', '')
                if not created_at:
                    # No timestamp → cannot verify freshness → DROP as stale
                    no_timestamp_count += 1
                    continue
                if cutoff_iso and created_at < cutoff_iso:
                    stale_count += 1
                    continue  # DROP stale order from previous day
                valid_orders.append(order)
            
            dropped_total = stale_count + no_timestamp_count
            if dropped_total > 0:
                logger.warning(
                    f"[DualAccountRevService] 🗑️ DROPPED {dropped_total} STALE REV orders "
                    f"for {account_id} (stale={stale_count}, no_timestamp={no_timestamp_count}, "
                    f"cutoff={cutoff_iso})"
                )
            
            if valid_orders:
                logger.info(f"[DualAccountRevService] Popped {len(valid_orders)} REV orders for {account_id}")
            
            return valid_orders
            
        except Exception as e:
            logger.error(f"[DualAccountRevService] Pop error: {e}")
            return []
    
    def get_queue_count(self, account_id: str) -> int:
        """Get number of pending REV orders for account"""
        try:
            key = REV_QUEUE_KEY_TEMPLATE.format(account_id=account_id)
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            return redis_sync.llen(key)
        except:
            return 0
    
    def clear_queue(self, account_id: str):
        """Clear all REV orders for account"""
        try:
            key = REV_QUEUE_KEY_TEMPLATE.format(account_id=account_id)
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            redis_sync.delete(key)
            logger.info(f"[DualAccountRevService] Cleared REV queue for {account_id}")
        except Exception as e:
            logger.error(f"[DualAccountRevService] Clear error: {e}")
    
    def flush_stale_queues(self):
        """
        Clear ALL session-specific Redis data for ALL accounts.
        
        MUST be called at Dual Process startup (daily reset).
        
        Clears:
        1. REV order queues — stale REV orders from yesterday
        2. Open orders — stale open order records from yesterday
        3. Duplicate order tracking — stale dedup keys
        
        DOES NOT clear:
        - Positions (psfalgo:positions:*) — refreshed by PositionSnapshot
        - BEFDAY (psfalgo:befday:*) — refreshed on market open
        - Market data (market:l1:*, tt:ticks:*) — live feed data
        - Fill events stream — historical record
        """
        if not self.redis_client:
            logger.warning("[DualAccountRevService] No Redis client — cannot flush")
            return
        
        redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
        
        for acct in ('HAMPRO', 'IBKR_PED', 'IBKR_GUN'):
            # 1. REV order queues
            try:
                rev_key = REV_QUEUE_KEY_TEMPLATE.format(account_id=acct)
                rev_count = redis_sync.llen(rev_key)
                if rev_count > 0:
                    redis_sync.delete(rev_key)
                    logger.warning(
                        f"[DualAccountRevService] 🗑️ DAILY RESET: Flushed {rev_count} "
                        f"stale REV orders from {acct} queue"
                    )
                else:
                    logger.info(f"[DualAccountRevService] DAILY RESET: {acct} REV queue already empty")
            except Exception as e:
                logger.error(f"[DualAccountRevService] REV flush error for {acct}: {e}")
            
            # 2. Open orders — yesterday's open orders are invalid today
            try:
                open_key = f"psfalgo:open_orders:{acct}"
                if redis_sync.exists(open_key):
                    redis_sync.delete(open_key)
                    logger.warning(
                        f"[DualAccountRevService] 🗑️ DAILY RESET: Cleared stale "
                        f"open_orders for {acct}"
                    )
            except Exception as e:
                logger.debug(f"[DualAccountRevService] open_orders flush error for {acct}: {e}")
        
        logger.info("[DualAccountRevService] ✅ All stale session data flushed (daily reset)")


# Global instance
_dual_account_rev_service: Optional[DualAccountRevService] = None


def get_dual_account_rev_service() -> DualAccountRevService:
    """Get or create global DualAccountRevService instance"""
    global _dual_account_rev_service
    if _dual_account_rev_service is None:
        _dual_account_rev_service = DualAccountRevService()
    return _dual_account_rev_service
