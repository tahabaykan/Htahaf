"""
REV Recovery Service

2 dakikada bir BEFDAY vs current positions check:
- Hangi pozisyonlarda fill oldu?
- REV order açılmış mı?
- Açılmamışsa create missing REV

ÖNEMLİ: Health kontrolü yalnızca hesap modu belirlenip, o hesap açılıp
pozisyonlar çekildikten SONRA yapılmalı. Önce hesap modu → sonra hesap aç →
sonra kontrol.

Pozisyonlar: fetch_snapshots_via_http verilirse backend’den (Pozisyonlar ekranı
ile aynı kaynak) çekilir; yoksa yerel PositionSnapshotAPI kullanılır.
Placement: placement_callback yoksa placement_http_fallback_url ile backend’e
POST atılır (take-profit/send-order).
"""

def _is_us_market_open() -> bool:
    """Check if US stock market is currently in regular trading hours.
    Returns True if current time is between 9:30 AM and 4:00 PM Eastern Time.
    """
    try:
        from zoneinfo import ZoneInfo
        et_now = datetime.now(ZoneInfo('America/New_York'))
        time_val = et_now.hour * 100 + et_now.minute
        return 930 <= time_val < 1600
    except Exception:
        return True
import asyncio
from typing import Dict, List, Any, Optional, Callable, Awaitable
from datetime import datetime
from loguru import logger

# When rev control skipped due to data not ready, retry after this many seconds
DATA_NOT_READY_RETRY_SECONDS = 20


class RevRecoveryService:
    """
    Recovery service for missing REV orders.
    
    Periodically checks:
    1. BEFDAY qty vs current qty
    2. Missing REV orders for fills
    3. Creates missing REVs

    Sıra: önce hangi hesap modu aktif → o hesabı aç / pozisyonları çek →
    ancak ondan sonra Health Equation kontrolü.
    """
    
    def __init__(
        self,
        redis_client,
        rev_engine,
        placement_callback=None,
        get_active_account: Optional[Callable[[], Awaitable[str]]] = None,
        ensure_account_ready: Optional[Callable[[str], Awaitable[None]]] = None,
        fetch_snapshots_via_http: Optional[Callable[[str], Awaitable[List[Any]]]] = None,
        placement_http_fallback_url: Optional[str] = "http://localhost:8000",
        get_recovery_ok_after: Optional[Callable[[], Optional[datetime]]] = None,
        data_ready_max_zero_both_ratio: float = 0.30,
        get_account_mode: Optional[Callable[[], Awaitable[str]]] = None,
    ):
        self.redis_client = redis_client
        self.rev_engine = rev_engine
        self.placement_callback = placement_callback
        self.get_active_account = get_active_account
        self.ensure_account_ready = ensure_account_ready
        self.fetch_snapshots_via_http = fetch_snapshots_via_http
        self.placement_http_fallback_url = placement_http_fallback_url or "http://localhost:8000"
        self.get_recovery_ok_after = get_recovery_ok_after
        self.data_ready_max_zero_both_ratio = data_ready_max_zero_both_ratio
        self.get_account_mode = get_account_mode  # Unified: same source as terminal
        self.running = False
        self._last_skip_reason = None  # 'data_not_ready' → retry in 20s
        self._backend_ready = False  # Cached backend readiness
        self._last_backend_check = 0  # Timestamp of last check
    
    def _is_backend_reachable(self) -> bool:
        """
        Quick health check: is localhost:8000 responding?
        Uses a very short timeout (1s) to avoid blocking.
        Caches result for 30s to avoid spamming.
        """
        import time
        now = time.time()
        # Cache for 30s
        if now - self._last_backend_check < 30:
            return self._backend_ready
        
        self._last_backend_check = now
        try:
            import requests
            resp = requests.get("http://localhost:8000/health", timeout=1)
            self._backend_ready = resp.status_code == 200
        except Exception:
            self._backend_ready = False
        return self._backend_ready
    
    async def start_periodic_check(self, interval_seconds: int = 120):
        """
        Start periodic recovery check (every 2 minutes).
        
        Args:
            interval_seconds: Check interval (default 120s =2 min)
        """
        self.running = True
        logger.info(f"[RevRecovery] Starting periodic check (every {interval_seconds}s)")
        
        while self.running:
            try:
                self._last_skip_reason = None
                await self._run_recovery_check()
                if getattr(self, '_last_skip_reason', None) == 'data_not_ready':
                    await asyncio.sleep(DATA_NOT_READY_RETRY_SECONDS)
                else:
                    await asyncio.sleep(interval_seconds)
            except Exception as e:
                logger.error(f"[RevRecovery] Error in periodic check: {e}", exc_info=True)
                await asyncio.sleep(interval_seconds)
    
    async def _run_recovery_check(self):
        """
        Run recovery check using Equation of Health.
        
        REV ONLY triggers when BOTH conditions are met:
          1. abs(befday - current) >= 200   (a fill actually happened)
          2. abs(befday - potential) >= 200  (open orders won't fix it)
        
        MARKET HOURS ONLY: 9:30-16:00 US Eastern Time.
        """
        # ── MARKET HOURS GUARD ──
        if not _is_us_market_open():
            logger.debug("[RevRecovery] Outside US market hours (9:30-16:00 ET). Skipping.")
            return
        try:
            # 1) Hangi hesap aktif? Terminal ile AYNI kaynağı kullan (get_account_mode callback)
            active_account = None
            if self.get_account_mode:
                try:
                    active_account = await self.get_account_mode()
                except Exception as e:
                    logger.debug(f"[RevRecovery] get_account_mode error: {e}")
            
            # Fallback: eski yöntem (get_active_account callback veya Redis)
            if not active_account and self.get_active_account:
                try:
                    active_account = await self.get_active_account()
                except Exception:
                    pass
            
            if not active_account:
                # Son çare: Doğrudan Redis'ten oku
                if self.redis_client:
                    try:
                        raw = self.redis_client.sync.get("psfalgo:recovery:account_open") if getattr(self.redis_client, 'sync', None) else None
                        if raw is not None:
                            active_account = (raw.decode() if isinstance(raw, bytes) else raw) or None
                    except Exception:
                        pass
            
            if not active_account:
                logger.info("[RevRecovery] No account open yet. Waiting for user to open at least one account. Skipping.")
                return
            
            # Normalize
            if active_account == "HAMMER_PRO":
                active_account = "HAMPRO"

            logger.info(f"[RevRecovery] Account: {active_account} — running health check")

            # 2) Hesabı aç (snapshot HTTP’den alınacaksa bağlantı zorunlu değil)
            if self.fetch_snapshots_via_http:
                pass  # Pozisyonlar backend’den alınacak; yerel IBKR bağlantısı gerekmez
            # 1b) Hesap seçildikten sonra 5s beklemeden rev kontrolü başlatma
            if self.get_recovery_ok_after:
                ok_after = self.get_recovery_ok_after()
                if ok_after and datetime.now() < ok_after:
                    logger.info("[RevRecovery] Waiting for 5s after account select/switch before rev control. Skipping this cycle.")
                    return

            # 2) Hesabı aç
            if self.fetch_snapshots_via_http:
                pass
            elif self.ensure_account_ready:
                await self.ensure_account_ready(active_account)
            else:
                await self._ensure_connection_builtin(active_account)

            # 3) Snapshot kaynağı: IBKR için yerel PositionSnapshotAPI (terminal IBKR'a bağlı);
            #    Hammer için HTTP (backend) veya yerel API.
            #    Backend'in IBKR bağlantısı yok; HTTP ile alınan snapshot'larda qty/potential_qty 0 gelir.
            snapshots: List[Any] = []
            use_http_for_snapshots = (
                self.fetch_snapshots_via_http
                and active_account not in ("IBKR_PED", "IBKR_GUN")
            )
            if use_http_for_snapshots:
                # Pre-check: is backend reachable? If not, skip HTTP fetch to avoid 15s timeout
                if not self._is_backend_reachable():
                    logger.debug(f"[RevRecovery] Backend not reachable, skipping HTTP snapshot fetch")
                    snapshots = []
                else:
                    try:
                        snapshots = await self.fetch_snapshots_via_http(active_account)
                        if snapshots is None:
                            snapshots = []
                        if isinstance(snapshots, dict) and "positions" in snapshots:
                            snapshots = snapshots.get("positions") or []
                        logger.info(f"[RevRecovery] Running Health Equation check for account: {active_account} (via backend)")
                    except Exception as e:
                        logger.warning(f"[RevRecovery] Backend fetch failed: {e}, using PositionSnapshotAPI")
                        snapshots = []
            if not snapshots:
                # CRITICAL FIX: Try Redis first (fast, no timeout, no connector needed)
                try:
                    if self.redis_client and getattr(self.redis_client, 'sync', None):
                        import json
                        positions_key = f"psfalgo:positions:{active_account}"
                        raw_positions = self.redis_client.sync.get(positions_key)
                        if raw_positions:
                            positions_dict = json.loads(raw_positions.decode() if isinstance(raw_positions, bytes) else raw_positions)
                            if positions_dict:
                                from types import SimpleNamespace
                                snapshots = [
                                    SimpleNamespace(
                                        symbol=sym,
                                        qty=pos_data.get('qty', 0),
                                        potential_qty=pos_data.get('potential_qty', 0),
                                        befday_qty=pos_data.get('befday_qty', 0),
                                        current_price=None
                                    )
                                    for sym, pos_data in positions_dict.items()
                                    if sym and sym != '_meta'
                                ]
                                logger.info(f"[RevRecovery] ✅ Read {len(snapshots)} positions from Redis (fast path, no connector needed)")
                except Exception as redis_err:
                    logger.debug(f"[RevRecovery] Redis read failed: {redis_err}")
                
                # Fallback: Use PositionSnapshotAPI (will try Redis first internally)
                if not snapshots:
                    from app.psfalgo.position_snapshot_api import get_position_snapshot_api
                    pos_api = get_position_snapshot_api()
                    if pos_api:
                        snapshots = await pos_api.get_position_snapshot(account_id=active_account)
                        logger.info(f"[RevRecovery] Running Health Equation check for account: {active_account} (PositionSnapshotAPI / Redis + IBKR)")
                    else:
                        logger.error("[RevRecovery] PositionSnapshotAPI not available")
                        return

            logger.info(f"[RevRecovery] Found {len(snapshots)} position snapshots for {active_account}")

            # 3b) Veri hazır mı? Portföyün %30'dan fazlasında hem current=0 hem potential=0 ise henüz veri gelmemiş
            total = len(snapshots)
            zero_both = 0
            for snap in snapshots:
                q = getattr(snap, 'qty', 0) if hasattr(snap, 'qty') else (snap.get('qty', 0) if isinstance(snap, dict) else 0)
                p = getattr(snap, 'potential_qty', 0) if hasattr(snap, 'potential_qty') else (snap.get('potential_qty', 0) if isinstance(snap, dict) else 0)
                try:
                    q, p = float(q or 0), float(p or 0)
                except (TypeError, ValueError):
                    q, p = 0.0, 0.0
                if abs(q) < 0.01 and abs(p) < 0.01:
                    zero_both += 1
            if total > 0 and zero_both > self.data_ready_max_zero_both_ratio * total:
                self._last_skip_reason = 'data_not_ready'
                logger.info(
                    f"[RevRecovery] Data not ready: {zero_both}/{total} positions have current=0 and potential=0 "
                    f"(>{self.data_ready_max_zero_both_ratio:.0%}). Retrying in {DATA_NOT_READY_RETRY_SECONDS}s."
                )
                return

            # 4) Health Equation kontrolü (BEFDAY / Current / Potential)
            # Pre-fetch open orders to skip symbols already being handled
            open_order_symbols = set()
            try:
                raw = self.redis_client.get(f"psfalgo:open_orders:{active_account}")
                if raw:
                    import json
                    data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                    orders = data if isinstance(data, list) else data.get('orders', [])
                    for order in orders:
                        sym = order.get('symbol', '') if isinstance(order, dict) else ''
                        if sym:
                            open_order_symbols.add(sym)
                if open_order_symbols:
                    logger.info(f"[RevRecovery] {len(open_order_symbols)} symbols have open orders (will skip)")
            except Exception:
                pass
            
            from types import SimpleNamespace
            for snap in snapshots:
                if isinstance(snap, dict):
                    snap = SimpleNamespace(
                        symbol=snap.get('symbol', ''),
                        befday_qty=float(snap.get('befday_qty', 0) or 0),
                        qty=float(snap.get('qty', 0) or 0),
                        potential_qty=float(snap.get('potential_qty', 0) or 0),
                        current_price=float(snap.get('current_price', 0) or 0) if snap.get('current_price') is not None else None,
                    )
                symbol = getattr(snap, 'symbol', '')
                befday = getattr(snap, 'befday_qty', 0) or 0
                potential = getattr(snap, 'potential_qty', 0) or 0
                current = getattr(snap, 'qty', 0) or 0
                
                # ── GAP CALCULATION ──
                # REV ONLY fires when befday differs from BOTH current AND potential.
                # ═══════════════════════════════════════════════════════════════
                # befday ≈ current  → No fills happened yet → No REV needed
                # befday ≈ potential → Open orders will bring position back → No REV needed
                # befday ≠ current AND befday ≠ potential → Fill happened AND
                #   open orders won't correct it → REV IS needed
                # ═══════════════════════════════════════════════════════════════
                current_gap = befday - current
                potential_gap = befday - potential
                
                # CONDITION 1: If befday ≈ current → no fill happened, nothing to reverse
                if abs(current_gap) < 200:
                    logger.debug(f"[RevRecovery] {symbol} Healthy: current≈befday (gap={current_gap:.0f})")
                    continue
                
                # CONDITION 2: If befday ≈ potential → open orders already correct the deviation
                if abs(potential_gap) < 200:
                    logger.debug(f"[RevRecovery] {symbol} Healthy: potential≈befday (gap={potential_gap:.0f})")
                    continue
                
                # Both gaps are significant → fill happened AND no open orders fix it
                effective_gap = potential_gap
                
                # Skip if this symbol already has an open order
                if symbol in open_order_symbols:
                    logger.debug(
                        f"[RevRecovery] ⏩ {symbol}: has open order, gap={effective_gap:.0f}"
                    )
                    continue
                
                logger.warning(
                    f"[RevRecovery] ⚠️ Health Broken: {symbol} "
                    f"befday={befday:.0f} current={current:.0f} potential={potential:.0f} "
                    f"→ gap={effective_gap:.0f}"
                )
                
                # Create Missing REV using effective_gap
                await self._create_missing_rev_from_gap(snap, effective_gap)
        
        except Exception as e:
            logger.error(f"[RevRecovery] Recovery check error: {e}", exc_info=True)

    async def _ensure_connection_builtin(self, account_id: str) -> None:
        """
        Hesap açılmadan pozisyon çekilmez. Callback yoksa built-in: IBKR için
        bağlantı kur. HAMPRO için burada bir şey yapmıyoruz (Hammer zaten session
        tarafından yönetiliyor).
        """
        if account_id not in ("IBKR_PED", "IBKR_GUN"):
            return
        try:
            from app.psfalgo.ibkr_connector import get_ibkr_connector
            conn = get_ibkr_connector(account_type=account_id)
            if conn and not conn.is_connected():
                logger.info(f"[RevRecovery] Connecting to {account_id} before fetching positions...")
                await conn.connect()
        except Exception as e:
            logger.warning(f"[RevRecovery] Built-in connect for {account_id} failed: {e}")

    async def _create_missing_rev_from_gap(self, snap: Any, gap: float):
        """Create REV order based on Health Gap"""
        try:
            symbol = snap.symbol
            befday = snap.befday_qty
            current = snap.qty
            potential = snap.potential_qty
            
            rev_action = 'BUY' if gap > 0 else 'SELL'
            tag_type = "UNKNOWN"
            
            # BEFDAY≈0: intraday/MM pozisyon — long/short CURRENT'a göre (RevnBookCheck ile aynı)
            if abs(befday) < 0.01:
                is_long = current > 0
                is_short = current < 0
            else:
                is_long = befday > 0
                is_short = befday < 0
            
            if is_long:
                if current > befday and potential > befday:
                    tag_type = "INC" # Long Increase -> SELL (TP)
                elif current < befday and potential < befday:
                    tag_type = "DEC" # Long Decrease -> BUY (Reload)
            elif is_short:
                if current < befday and potential < befday:
                    tag_type = "INC" # Short Increase -> BUY (TP)
                elif current > befday and potential > befday:
                    tag_type = "DEC" # Short Decrease -> SELL (Reload)
            
            if tag_type == "UNKNOWN":
                logger.warning(f"[RevRecovery] {symbol} Could not determine REV scenario (Bef:{befday}, Cur:{current}, Pot:{potential})")
                return
            
            # Build proper tag for RevOrderEngine to parse
            # Must include {SOURCE}_{DIRECTION}_{ACTION} for unified tag format
            direction = "LONG" if is_long else "SHORT"
            source = "MM"  # Recovery REVs default to MM source
            pseudo_tag = f"{source}_{direction}_{tag_type}"  # e.g., MM_LONG_INC
            
            # Reconstruct pseudo-fill for the engine
            # Determine which fill action we need to look for (opposite of rev_action)
            # If rev_action is SELL (we need to sell to reload), the original fill was a SELL
            # If rev_action is BUY (we need to buy to reload), the original fill was a BUY
            # 
            # CRITICAL: For DEC (reload) scenarios:
            #   - If we SOLD shares intraday (gap > 0, befday > potential), we need to BUY to reload
            #   - The fill_action we look for is SELL (the action that caused the gap)
            #   - If we BOUGHT shares intraday (gap < 0, befday < potential), we need to SELL to reload
            #   - The fill_action we look for is BUY
            fill_action_to_find = 'SELL' if gap > 0 else 'BUY'
            
            # 1. Try to find the actual last fill price from multi-source lookup
            fill_result = await self._get_last_fill_price(symbol, required_action=fill_action_to_find)
            
            fill_price = None
            if fill_result:
                fill_price = fill_result['price']
                logger.info(f"[RevRecovery] Found {fill_result['action']} fill for {symbol}: "
                           f"{fill_result['qty']} @ ${fill_price:.2f} (source: {fill_result['source']})")
            
            # 2. Fallback to current snapshot price if no fill found
            if not fill_price:
                fill_price = getattr(snap, 'current_price', None) or 0.0
                if fill_price > 0:
                    logger.info(f"[RevRecovery] Using Snapshot Price fallback for {symbol}: ${fill_price:.2f}")
            
            # 3. Son çare: pozisyon ortalama maliyeti (Hammer'da fiyat yoksa)
            if not fill_price or fill_price <= 0:
                fill_price = float(getattr(snap, 'avg_price', 0) or 0)
                if fill_price > 0:
                    logger.info(f"[RevRecovery] Using Avg Price fallback for {symbol}: ${fill_price:.2f}")
            
            if fill_price == 0.0:
                logger.warning(f"[RevRecovery] No price data found for {symbol} (Ledger or Snap or Avg), cannot calculate REV")
                return
                
            pseudo_fill = {
                'symbol': symbol,
                'action': 'BUY' if rev_action == 'SELL' else 'SELL',
                'qty': abs(gap),
                'price': fill_price,
                'tag': pseudo_tag,
                'order_id': f"rec_{symbol}_{int(datetime.now().timestamp())}"
            }
            
            # Get L1 for pricing
            l1_data = await self._get_l1_data(symbol)
            
            # Calculate REV order
            rev_order = self.rev_engine.calculate_rev_order(pseudo_fill, l1_data)
            
            if not rev_order:
                return
            success = False
            if self.placement_callback:
                success = await self.placement_callback(rev_order)
            elif self.placement_http_fallback_url:
                success = await self._place_rev_via_http(rev_order)
            
            if success:
                logger.info(
                    f"[RevRecovery] ✓ Recovery REV placed: {rev_order['tag']} "
                    f"{rev_order['action']} {rev_order['qty']} @ ${rev_order['price']:.2f}"
                )
            else:
                if self.placement_callback:
                    logger.error(f"[RevRecovery] ✗ Failed to place recovery REV for {symbol} (callback returned False)")
                elif self.placement_http_fallback_url:
                    logger.error(f"[RevRecovery] ✗ Failed to place recovery REV for {symbol} (HTTP request failed or returned success=False)")
                else:
                    logger.warning(f"[RevRecovery] Placement callback and HTTP fallback missing for {symbol}")
                
        except Exception as e:
            logger.error(f"[RevRecovery] Create missing REV error for {snap.symbol}: {e}")

    async def _get_last_fill_price(self, symbol: str, required_action: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Query fill price for the day from multiple sources.
        
        MULTI-SOURCE LOOKUP:
        1. Redis Stream (real-time, fast)
        2. CSV Files (persistent, survives restarts/disconnects)
        
        Args:
            symbol: The stock symbol
            required_action: Optional filter - 'BUY' or 'SELL' to find specific fill type
            
        Returns:
            Dict with {'price': float, 'action': str, 'qty': float, 'source': str} or None
        """
        # ═══════════════════════════════════════════════════════════════════
        # SOURCE 1: Redis Stream (most recent, real-time)
        # ONLY use fills from TODAY's US market hours (9:30-16:00 ET)
        # ═══════════════════════════════════════════════════════════════════
        try:
            from zoneinfo import ZoneInfo
            et_tz = ZoneInfo('America/New_York')
            et_now = datetime.now(et_tz)
            # Today's market open: 9:30 ET
            market_open_et = et_now.replace(hour=9, minute=30, second=0, microsecond=0)
            # Convert to Unix millis for Redis stream ID filter
            market_open_ms = int(market_open_et.timestamp() * 1000)
            min_stream_id = f"{market_open_ms}-0"
            
            ledger_key = "psfalgo:execution:ledger"
            entries = self.redis_client.sync.xrevrange(
                ledger_key, max='+', min=min_stream_id, count=500
            )
            
            if entries:
                for entry_id, data in entries:
                    decoded = {k.decode() if isinstance(k, bytes) else k: 
                              v.decode() if isinstance(v, bytes) else v 
                              for k, v in data.items()}
                    
                    if decoded.get('symbol') == symbol:
                        action = decoded.get('action', decoded.get('side', '')).upper()
                        # Filter by action if required
                        if required_action and action != required_action.upper():
                            continue
                        price = float(decoded.get('price', 0))
                        qty = float(decoded.get('qty', 0))
                        if price > 0:
                            logger.info(f"[RevRecovery] Found Fill in Redis Stream for {symbol}: {action} {qty} @ ${price:.2f}")
                            return {'price': price, 'action': action, 'qty': qty, 'source': 'redis_stream'}
        except Exception as e:
            logger.debug(f"[RevRecovery] Redis stream query failed for {symbol}: {e}")
        
        # ═══════════════════════════════════════════════════════════════════
        # SOURCE 2: CSV Files (persistent, survives disconnects)
        # ═══════════════════════════════════════════════════════════════════
        try:
            from app.trading.daily_fills_store import get_daily_fills_store
            import os
            import csv
            
            fills_store = get_daily_fills_store()
            
            # Get active account to determine CSV file
            active_account = None
            if self.get_active_account:
                try:
                    active_account = await self.get_active_account()
                except:
                    pass
            if not active_account:
                # Try Redis
                try:
                    raw = self.redis_client.sync.get("psfalgo:recovery:account_open")
                    if raw:
                        active_account = raw.decode() if isinstance(raw, bytes) else raw
                except:
                    pass
            
            if active_account:
                filename = fills_store._get_filename(active_account)
                filepath = os.path.join(fills_store.log_dir, filename)
                
                if os.path.exists(filepath):
                    # Read CSV in reverse order (most recent first)
                    with open(filepath, 'r') as f:
                        rows = list(csv.DictReader(f))
                    
                    # Reverse to get most recent first
                    for row in reversed(rows):
                        if row.get("Symbol") == symbol:
                            action = row.get("Action", "").upper()
                            # Filter by action if required
                            if required_action and action != required_action.upper():
                                continue
                            price = float(row.get("Price", 0))
                            qty = float(row.get("Quantity", 0))
                            if price > 0:
                                logger.info(f"[RevRecovery] Found Fill in CSV for {symbol}: {action} {qty} @ ${price:.2f}")
                                return {'price': price, 'action': action, 'qty': qty, 'source': 'csv'}
        except Exception as e:
            logger.debug(f"[RevRecovery] CSV query failed for {symbol}: {e}")
        
        # ═══════════════════════════════════════════════════════════════════
        # SOURCE 3: Hammer API (via getTransactions - works even after reconnect)
        # Only if HAMPRO mode is active
        # ═══════════════════════════════════════════════════════════════════
        try:
            # Check if account is HAMPRO
            active_account = None
            if self.get_active_account:
                try:
                    active_account = await self.get_active_account()
                except:
                    pass
            if not active_account:
                try:
                    raw = self.redis_client.sync.get("psfalgo:recovery:account_open")
                    if raw:
                        active_account = raw.decode() if isinstance(raw, bytes) else raw
                except:
                    pass
            
            # ─────────────────────────────────────────────────────────────
            # SOURCE 3a: Hammer API (for HAMPRO mode)
            # ─────────────────────────────────────────────────────────────
            if active_account and "HAMPRO" in str(active_account).upper():
                from app.live.hammer_client import get_hammer_client
                hammer = get_hammer_client()
                if hammer and hammer.is_connected():
                    # Request transactions (this triggers transactionsUpdate)
                    resp = hammer.get_transactions(timeout=3.0)
                    if resp and resp.get('success') == 'OK':
                        logger.debug(f"[RevRecovery] Hammer getTransactions sent for {symbol}")
            
            # ─────────────────────────────────────────────────────────────
            # SOURCE 3b: IBKR API (for IBKR_PED/IBKR_GUN modes)
            # Uses IBKRConnector.get_filled_orders() to get today's fills
            # ─────────────────────────────────────────────────────────────
            elif active_account and "IBKR" in str(active_account).upper():
                try:
                    from app.psfalgo.ibkr_connector import get_ibkr_connector
                    
                    # Use active_account directly (e.g., "IBKR_PED" or "IBKR_GUN")
                    account_type = str(active_account).upper()
                    connector = get_ibkr_connector(account_type=account_type, create_if_missing=False)
                    if connector and connector.is_connected():
                        # Get today's filled orders
                        filled_orders = await connector.get_filled_orders()
                        
                        if filled_orders:
                            # Find most recent fill for this symbol with matching action
                            for fill in reversed(filled_orders):  # Most recent first
                                if fill.get('symbol') == symbol:
                                    fill_action = fill.get('action', '').upper()
                                    # Filter by action if required
                                    if required_action and fill_action != required_action.upper():
                                        continue
                                    
                                    fill_price = float(fill.get('price', 0))
                                    fill_qty = float(fill.get('qty', 0))
                                    
                                    if fill_price > 0:
                                        logger.info(f"[RevRecovery] Found Fill in IBKR API for {symbol}: "
                                                   f"{fill_action} {fill_qty} @ ${fill_price:.2f}")
                                        return {
                                            'price': fill_price, 
                                            'action': fill_action, 
                                            'qty': fill_qty, 
                                            'source': 'ibkr_api'
                                        }
                except Exception as ibkr_err:
                    logger.debug(f"[RevRecovery] IBKR API query failed for {symbol}: {ibkr_err}")
                    
        except Exception as e:
            logger.debug(f"[RevRecovery] Broker API query failed for {symbol}: {e}")
        
        logger.warning(f"[RevRecovery] No fill found for {symbol} in Redis, CSV, or Broker API")
        return None
    
    async def _get_last_fill_price_simple(self, symbol: str) -> Optional[float]:
        """Backward compatible wrapper - returns just the price"""
        result = await self._get_last_fill_price(symbol)
        return result['price'] if result else None

    async def _get_l1_data(self, symbol: str) -> Dict[str, Any]:
        """Get L1 market data from Redis (market:l1:{symbol} then fallback market_data:snapshot:{symbol})"""
        try:
            import json
            key = f"market:l1:{symbol}"
            data = self.redis_client.sync.get(key)
            if data:
                l1 = json.loads(data)
                bid = float(l1.get('bid', 0))
                ask = float(l1.get('ask', 0))
                spread = float(l1.get('spread', 0))
                if spread == 0 and bid and ask:
                    spread = ask - bid
                if bid or ask:
                    return {'bid': bid, 'ask': ask, 'spread': spread}
            # Fallback: snapshot scheduler / backend writes market_data:snapshot:{symbol} (bid/ask/last)
            snap_key = f"market_data:snapshot:{symbol}"
            snap_data = self.redis_client.sync.get(snap_key)
            if snap_data:
                snap = json.loads(snap_data)
                bid = float(snap.get('bid', 0))
                ask = float(snap.get('ask', 0))
                spread = float(snap.get('spread', 0)) if snap.get('spread') else (ask - bid if (bid and ask) else 0)
                if bid or ask:
                    return {'bid': bid, 'ask': ask, 'spread': spread}
            return {'bid': 0.0, 'ask': 0.0, 'spread': 0.0}
        except Exception as e:
            return {'bid': 0.0, 'ask': 0.0, 'spread': 0.0}

    async def _place_rev_via_http(self, rev_order: Dict[str, Any]) -> bool:
        """Place REV via backend take-profit/send-order when placement_callback is missing. account_id = aktif hesap (Hammer vs IBKR Gateway)."""
        account_id = None
        if self.get_active_account:
            try:
                account_id = await self.get_active_account()
                if account_id == "HAMMER_PRO":
                    account_id = "HAMPRO"
            except Exception:
                pass
        payload = {
            "symbol": rev_order.get("symbol", ""),
            "side": rev_order.get("action", "BUY"),
            "qty": int(rev_order.get("qty", 0)),
            "price": float(rev_order.get("price", 0)),
            "order_type": "LIMIT",
        }
        if account_id:
            payload["account_id"] = account_id

        def _post():
            import requests
            url = self.placement_http_fallback_url.rstrip("/") + "/api/psfalgo/take-profit/send-order"
            try:
                r = requests.post(url, json=payload, timeout=6)
                if r.status_code != 200:
                    logger.error(f"[RevRecovery] HTTP place failed: status={r.status_code}, response={r.text[:200]}")
                    return False
                result = r.json() or {}
                success = result.get("success", False)
                if not success:
                    logger.error(f"[RevRecovery] HTTP place returned success=False: {result.get('detail') or result.get('error') or result}")
                return success
            except Exception as e:
                logger.error(f"[RevRecovery] HTTP place exception: {e}")
                return False

        try:
            # Pre-check: backend reachable?
            if not self._is_backend_reachable():
                logger.debug(f"[RevRecovery] Backend not reachable, skipping HTTP REV placement for {rev_order.get('symbol')}")
                return False
            
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _post)
        except Exception as e:
            logger.error(f"[RevRecovery] HTTP place error for {rev_order.get('symbol')}: {e}")
            return False
    
    def stop(self):
        """Stop periodic check"""
        self.running = False
        logger.info("[RevRecovery] Stopping periodic check")


# Global instance
_rev_recovery_service = None


def get_rev_recovery_service():
    """Get or create global RevRecoveryService instance"""
    global _rev_recovery_service
    
    if _rev_recovery_service is None:
        # Import dependencies
        from app.core.redis_client import get_redis_client
        from app.terminals.revorder_engine import get_revorder_engine
        
        redis_client = get_redis_client()
        rev_engine = get_revorder_engine()
        
        _rev_recovery_service = RevRecoveryService(redis_client, rev_engine)
        logger.info("[RevRecoveryService] Global instance created")
    
    return _rev_recovery_service
