"""
RevnBookCheck Terminal

Auto REV Order Generator - monitors fills and creates TP/Reload orders.
PLUS: Frontlama Engine - evaluates active orders for front-run opportunities.

Frontlama runs every 60 seconds and checks ALL active orders against:
- Valid truth ticks
- Sacrifice limits (cent + ratio)
- Exposure-based adjustments

When user selects an account (HAMPRO, IBKR_PED, IBKR_GUN): wait 5s before starting
rev order control (data loads as 0 initially). Before running health gap scan,
require at least 70% of positions to have (current≠0 OR potential≠0); if more
than 30% have both 0, data not ready — skip until next cycle.
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from loguru import logger

# Wait this long after account select/switch before running rev order control
REV_ACCOUNT_SETTLE_SECONDS = 5
# Max share of portfolio that may have both current=0 and potential=0; above = data not ready
REV_DATA_READY_MAX_ZERO_BOTH_RATIO = 0.30  # i.e. at least 70% must have some data

from app.terminals.revorder_engine import RevOrderEngine
from app.terminals.revorder_config import load_revorder_config
from app.terminals.frontlama_engine import get_frontlama_engine, FrontlamaDecision


class RevnBookCheckTerminal:
    """
    RevnBookCheck Terminal - Auto REV Order Generator
    
    Features:
    - Monitor fills in real-time
    - Generate REV orders (TP/Reload)
    - OrderBook analysis
    - Recovery on startup
    """
    
    def __init__(self):
        self.config = load_revorder_config()
        self.rev_engine = RevOrderEngine(self.config)
        self.running = False
        
        # Redis and account mode
        self.redis_client = None
        self.account_mode = 'IBKR_GUN'  # Default
        # After account select/switch: do not run rev control until this time (5s settle)
        self._recovery_ok_after: Optional[datetime] = None
        
        # Initialize Redis
        self._init_redis()
        
        # Recovery service: hesap modu, "hesap açıldıktan sonra kontrol", snapshot backend’den
        from app.terminals.rev_recovery_service import RevRecoveryService
        self.recovery_service = RevRecoveryService(
            redis_client=self.redis_client,
            rev_engine=self.rev_engine,
            placement_callback=self._place_rev_order,
            get_active_account=self._get_account_for_recovery,
            ensure_account_ready=self._ensure_account_ready_for_recovery,
            fetch_snapshots_via_http=self._fetch_snapshots_from_backend,
            placement_http_fallback_url="http://localhost:8000",
            get_recovery_ok_after=self._get_recovery_ok_after,
            data_ready_max_zero_both_ratio=REV_DATA_READY_MAX_ZERO_BOTH_RATIO,
            get_account_mode=self._get_unified_account_mode,
        )
        
        # ═══════════════════════════════════════════════════════════════════
        # FRONTLAMA ENGINE - runs every 60 seconds
        # ═══════════════════════════════════════════════════════════════════
        self.frontlama_engine = get_frontlama_engine()
        self.frontlama_interval = 60  # seconds
        
        logger.info("[RevnBookCheck] Terminal initialized (with Frontlama Engine)")
    
    async def start(self):
        """Start terminal"""
        logger.info("=" * 80)
        logger.info("[RevnBookCheck] Starting terminal...")
        logger.info(f"[RevnBookCheck] Config: INC profit={self.config.inc_min_profit}, DEC save={self.config.dec_min_save}")
        logger.info("=" * 80)
        
        # İlk hesap modu: Redis'te açık hesap yoksa account_mode (seçili), yoksa default
        self.account_mode = await self._get_active_account_from_redis()
        logger.info(f"[RevnBookCheck] Initial account: {self.account_mode or '(no account open yet)'}")
        
        # Açık hesap varsa bağlantı kur; 5s bekle (veri 0 gelir yoksa), sonra recovery
        if self.account_mode:
            await self._ensure_connections()
            self._recovery_ok_after = datetime.now() + timedelta(seconds=REV_ACCOUNT_SETTLE_SECONDS)
            logger.info(f"[RevnBookCheck] Waiting {REV_ACCOUNT_SETTLE_SECONDS}s for data to load before first recovery...")
            await asyncio.sleep(REV_ACCOUNT_SETTLE_SECONDS)
            await self._startup_recovery()
        
        # Start fill event monitoring + Recovery + Frontlama + MM Exit Guard + **hesap modu senkronu (15s)**
        self.running = True
        
        # Initialize MM Exit Guard
        from app.mm.mm_exit_guard import get_mm_exit_guard
        self._mm_exit_guard = get_mm_exit_guard()
        
        await asyncio.gather(
            self._subscribe_fill_events(),                     # Stream monitoring
            self.recovery_service.start_periodic_check(120),   # 2-minute recovery checks
            self._frontlama_loop(),                            # 60-second frontlama checks
            self._account_sync_loop(),                         # Her 15s: hesap açık mı, health gap + REV order
            self._mm_exit_guard.start_periodic_check(),        # 30-second MM exit guard checks
            return_exceptions=True
        )
    
    async def _startup_recovery(self):
        """Run recovery scan. BEFDAY/positions önce Redis, yoksa backend (Pozisyonlar ile aynı kaynak)."""
        logger.info("[RevnBookCheck] Running startup recovery...")
        
        try:
            befday_data = await self._get_befday_data()
            positions = await self._get_positions()
            # Redis boşsa backend’den dene (Pozisyonlar ekranı ile aynı kaynak)
            if not positions and not befday_data:
                try:
                    snapshots = await self._fetch_snapshots_from_backend(self.account_mode)
                    if snapshots:
                        positions = [{"symbol": getattr(s, "symbol", ""), "qty": getattr(s, "qty", 0)} for s in snapshots]
                        befday_data = {getattr(s, "symbol", ""): getattr(s, "befday_qty", 0) for s in snapshots if getattr(s, "befday_qty", 0)}
                        logger.info(f"[RevnBookCheck] Startup: using backend fallback — {len(positions)} positions, {len(befday_data)} with BEFDAY")
                except Exception as e:
                    logger.debug(f"[RevnBookCheck] Backend fallback for startup: {e}")
            open_orders = await self._get_open_orders()
            logger.info(
                f"[RevnBookCheck] Recovery complete: "
                f"{len(positions)} positions, {len(befday_data)} BEFDAY entries, "
                f"{len(open_orders)} open orders"
            )
            # İlk health gap taramasını hemen çalıştır (BEFDAY≠CURRENT/POTENTIAL → REV)
            try:
                await self.recovery_service._run_recovery_check()
            except Exception as e:
                logger.debug(f"[RevnBookCheck] Startup health check: {e}")
        except Exception as e:
            logger.error(f"[RevnBookCheck] Recovery error: {e}", exc_info=True)
            
    async def _get_account_for_recovery(self) -> str:
        """RevRecoveryService için: terminal'in aktif hesap modunu döndürür (recovery ile aynı kaynak)."""
        return await self._get_unified_account_mode()

    async def _get_unified_account_mode(self) -> str:
        """Tek kaynak: Terminal ve Recovery aynı hesabı kullanır.
        
        Priority:
        1. psfalgo:recovery:account_open → Connect API ile açılan hesap (en güvenilir)
        2. psfalgo:xnl:running_account → XNL Engine'in çalıştığı hesap  
        3. psfalgo:account_mode → UI'da seçili mod
        4. self.account_mode → cached fallback
        """
        active = await self._get_active_account_from_redis()
        if active:
            if active != self.account_mode:
                logger.info(f"[RevnBookCheck] Account mode updated: {self.account_mode} → {active}")
                self.account_mode = active
            return active
        return self.account_mode or "IBKR_GUN"

    def _get_recovery_ok_after(self) -> Optional[datetime]:
        """RevRecoveryService için: hesap seçildikten sonra rev kontrolü bu zamana kadar başlamasın."""
        return getattr(self, '_recovery_ok_after', None)

    async def _fetch_snapshots_from_backend(self, account_id: str):
        """
        RevRecoveryService için: Pozisyonlar ekranı ile aynı kaynak (backend).
        GET /api/trading/positions?account_id=X → snapshot benzeri objeler döner.
        Böylece terminalde IBKR 0 pozisyon döndürse bile backend’deki CURRENT/POTENTIAL kullanılır.
        """
        from types import SimpleNamespace
        import asyncio

        def _get():
            import requests
            url = "http://localhost:8000/api/trading/positions"
            r = requests.get(url, params={"account_id": account_id}, timeout=15)
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
            return out
        except Exception as e:
            logger.warning(f"[RevnBookCheck] Backend positions fetch failed for {account_id}: {e}")
            return []

    async def _ensure_account_ready_for_recovery(self, account_id: str) -> None:
        """RevRecoveryService için: Health kontrolünden önce o hesabı aç, pozisyonlar çekilebilsin."""
        if 'IBKR' in account_id:
            from app.psfalgo.ibkr_connector import get_ibkr_connector, get_active_ibkr_account
            # CRITICAL FIX: Terminal should NOT connect - backend API manages connections
            active_account = get_active_ibkr_account()
            conn = get_ibkr_connector(account_type=account_id, create_if_missing=False)
            if conn and conn.is_connected():
                logger.info(f"[RevnBookCheck] Backend connection exists for {account_id}, ready for recovery")
            elif active_account == account_id:
                logger.info(f"[RevnBookCheck] Backend has {account_id} as active, connection should be available")
            else:
                logger.warning(f"[RevnBookCheck] Backend not connected to {account_id} (active={active_account}). Recovery will wait for backend connection.")
                # Terminal should NOT connect itself - backend API manages connections

    async def _ensure_connections(self):
        """Ensure active connections for IBKR/Hammer for position data (aktif hesap = self.account_mode)."""
        try:
            if not self.account_mode:
                return
            # 1. IBKR Connection (if applicable)
            if 'IBKR' in self.account_mode:
                from app.psfalgo.ibkr_connector import get_ibkr_connector, get_active_ibkr_account
                
                # CRITICAL FIX: Check if backend already has connection before connecting
                # Backend API manages IBKR connections, terminal should NOT create its own
                active_account = get_active_ibkr_account()
                conn = get_ibkr_connector(account_type=self.account_mode, create_if_missing=False)
                
                if conn and conn.is_connected():
                    logger.info(f"[RevnBookCheck] Backend already connected to {self.account_mode}, using existing connection")
                elif active_account == self.account_mode:
                    logger.info(f"[RevnBookCheck] Backend has {self.account_mode} as active account, connection should exist")
                    # Wait a bit for backend connection to establish
                    await asyncio.sleep(1)
                    conn = get_ibkr_connector(account_type=self.account_mode, create_if_missing=False)
                    if conn and conn.is_connected():
                        logger.info(f"[RevnBookCheck] Backend connection verified for {self.account_mode}")
                    else:
                        logger.warning(f"[RevnBookCheck] Backend connection not ready for {self.account_mode}, terminal will wait for backend")
                else:
                    logger.warning(f"[RevnBookCheck] Backend not connected to {self.account_mode} (active={active_account}). Terminal will use backend connection when available.")
                    # Terminal should NOT connect itself - backend API manages connections
                    # Terminal will use backend's connection via PositionSnapshotAPI
            
            # 2. Daily Fills Store (Ensure initialized)
            from app.trading.daily_fills_store import get_daily_fills_store
            get_daily_fills_store() # trigger init
            
            logger.info("[RevnBookCheck] Connections verified")
        except Exception as e:
            logger.error(f"[RevnBookCheck] Connection initialization error: {e}")
    
    async def _process_fill(self, fill: Dict[str, Any], target_account: str = None, queue_for_later: bool = False):
        """
        Process fill using the Equation of Health:
        Gap = BEFDAY - POTENTIAL
        Trigger REV if abs(Gap) >= 200
        
        Args:
            fill: Fill event data (symbol, action, qty, price, etc.)
            target_account: Account to use for position lookup (defaults to self.account_mode).
                           In Dual Process cross-account fills, this is the OTHER account.
            queue_for_later: If True, queue REV order to Redis instead of placing directly.
                            Used for cross-account fills in Dual Process mode.
        """
        symbol = fill['symbol']
        active_account = target_account or self.account_mode or "IBKR_GUN"
        
        # ═══════════════════════════════════════════════════════════════
        # CRITICAL: Apply fill qty to Redis positions cache BEFORE snapshot
        # Without this, get_position_snapshot reads PRE-fill qty from Redis
        # and the Gap always comes out as 0 (HEALTHY) even after real fills.
        # ═══════════════════════════════════════════════════════════════
        try:
            import json as _json
            from app.core.redis_client import get_redis_client
            redis = get_redis_client()
            if redis:
                positions_key = f"psfalgo:positions:{active_account}"
                raw = redis.get(positions_key)
                if raw:
                    positions_dict = _json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                    if symbol in positions_dict and isinstance(positions_dict[symbol], dict):
                        fill_qty = float(fill.get('qty', 0))
                        fill_action = fill.get('action', '').upper()
                        # BUY adds qty, SELL subtracts qty
                        delta = fill_qty if fill_action == 'BUY' else -fill_qty
                        
                        old_qty = float(positions_dict[symbol].get('qty', 0))
                        new_qty = old_qty + delta
                        positions_dict[symbol]['qty'] = new_qty
                        
                        # Also update potential_qty (will be recalculated from open orders later)
                        old_potential = float(positions_dict[symbol].get('potential_qty', old_qty))
                        positions_dict[symbol]['potential_qty'] = old_potential + delta
                        
                        redis.set(positions_key, _json.dumps(positions_dict), ex=3600)
                        logger.info(
                            f"[RevnBookCheck] 📊 Applied fill to Redis: {symbol} "
                            f"{fill_action} {fill_qty} → qty {old_qty:.0f} → {new_qty:.0f}"
                        )
        except Exception as apply_err:
            logger.warning(f"[RevnBookCheck] Failed to apply fill to Redis cache: {apply_err}")
        
        # ── NEWCLMM EXCLUSION ──
        # NEWC-tagged fills have their own truth-tick-based TP mechanism.
        # REV must NOT process them — NEWCLMM manages its own exit cycle.
        fill_tag_upper = (fill.get('tag', '') or '').upper()
        if 'NEWC' in fill_tag_upper:
            logger.info(
                f"[RevnBookCheck] {symbol} SKIP: NEWC-tagged fill "
                f"(tag={fill_tag_upper}). NEWCLMM manages its own profit-taking."
            )
            return

        # ── ACTMAN DECREASE EXCLUSION ──
        # ACTMAN DEC fills are FINAL position reductions.
        # REV reload MUST NOT be written for these fills.
        # DEC tags: LT_ACTHEDGE_LONG_DEC, LT_ACTHEDGE_SHORT_DEC,
        #           LT_ACTPANIC_LONG_DEC, LT_ACTPANIC_SHORT_DEC
        if 'ACTHEDGE' in fill_tag_upper and '_DEC' in fill_tag_upper:
            logger.info(
                f"[RevnBookCheck] {symbol} SKIP: ACTMAN HEDGER DEC fill "
                f"(tag={fill_tag_upper}). DEC = final reduction, NO REV reload."
            )
            return
        if 'ACTPANIC' in fill_tag_upper and '_DEC' in fill_tag_upper:
            logger.info(
                f"[RevnBookCheck] {symbol} SKIP: ACTMAN PANIC DEC fill "
                f"(tag={fill_tag_upper}). DEC = final reduction, NO REV reload."
            )
            return
        
        # 1. Get Position Snapshot (Triad)
        from app.psfalgo.position_snapshot_api import get_position_snapshot_api
        pos_api = get_position_snapshot_api()
        if not pos_api:
            logger.error("[RevnBookCheck] PositionSnapshotAPI not available")
            return
            
        # Use target_account for position lookup (supports cross-account fills)
        snapshots = await pos_api.get_position_snapshot(account_id=active_account, symbols=[symbol])
        if not snapshots:
            logger.warning(f"[RevnBookCheck] No position data for {symbol} after fill")
            return
            
        snap = snapshots[0]
        befday = snap.befday_qty
        potential = snap.potential_qty
        current = snap.qty
        
        # 2. Check Equation of Health (Triple Equality)
        # Gap = What we SHOULD have (Befday) - What we WILL have (Potential)
        gap = befday - potential
        
        # RULE 1: Tolerance check
        if abs(gap) < 200:
            logger.info(f"[RevnBookCheck] {symbol} HEALTHY after fill (Bef={befday:.0f}, Cur={current:.0f}, Pot={potential:.0f}, Gap={gap:.0f})")
            return

        # RULE 2: Triple Equality - Skip if current target is met or will be met
        # CRITICAL FIX: Use float-safe comparison (0.01 tolerance) instead of ==
        # Float == fails for values like 2000.0000001 vs 2000.0
        if abs(befday - current) < 0.01:
            logger.info(f"[RevnBookCheck] {symbol} Skip: BEFDAY ≈ CURRENT ({befday:.0f})")
            return
            
        if abs(befday - potential) < 0.01:
            logger.info(f"[RevnBookCheck] {symbol} Skip: BEFDAY ≈ POTENTIAL ({befday:.0f})")
            return

        logger.info(f"[RevnBookCheck] ⚠️ Health Broken for {symbol}: Befday={befday:.0f}, Current={current:.0f}, Potential={potential:.0f}, Gap={gap:.0f}")

        # 3. Determine REV Scenario (4-Quadrant Mapping)
        rev_action = 'BUY' if gap > 0 else 'SELL'
        tag_type = "UNKNOWN"
        
        # ═══════════════════════════════════════════════════════════════════
        # MM POZİSYON DESTEĞİ: befday=0 olabilir (intraday açılan pozisyon)
        # Bu durumda current_qty'ye bakarak LONG/SHORT belirlenir
        # ═══════════════════════════════════════════════════════════════════
        if abs(befday) < 0.01:
            # MM/Intraday pozisyon - current'a bak
            is_long = current > 0
            is_short = current < 0
            logger.info(f"[RevnBookCheck] {symbol} MM/Intraday pozisyon (befday≈0), current={current} → {'LONG' if is_long else 'SHORT' if is_short else 'FLAT'}")
        else:
            is_long = befday > 0
            is_short = befday < 0
        
        # ═══════════════════════════════════════════════════════════════════
        # 8-TAG SİSTEMİ İLE TAG BELİRLEME (v4 format)
        # ═══════════════════════════════════════════════════════════════════
        # v4 tag format: {POS}_{ENGINE}_{DIR}_{ACTION}
        # POS = MM or LT (from fill tag or Redis PositionTagStore)
        # ENGINE = MM, KB, TRIM, PA, AN (from fill tag)
        # ═══════════════════════════════════════════════════════════════════
        
        # Determine POS TAG and ENGINE TAG from original fill tag
        original_tag = fill.get('tag', '').upper()
        clean_tag = original_tag.replace('FR_', '').replace('OZEL_', '')
        
        # Extract POS TAG: v4 first part, or Redis lookup, or default
        strategy_prefix = "MM"  # Default
        engine_prefix = "MM"    # Default engine
        
        tag_parts = clean_tag.split('_')
        if len(tag_parts) >= 4 and tag_parts[0] in ('MM', 'LT'):
            # v4 format: MM_KB_LONG_DEC → POS=MM, ENGINE=KB
            strategy_prefix = tag_parts[0]
            if tag_parts[1] in ('MM', 'PA', 'AN', 'KB', 'TRIM', 'NEWC'):
                engine_prefix = tag_parts[1]
        elif abs(befday) < 0.01:
            # befday≈0 → intraday position, check Redis PositionTagStore for actual POS TAG
            try:
                from app.psfalgo.position_tag_store import get_position_tag_store
                _store = get_position_tag_store()
                if _store:
                    _redis_pos = _store.get_tag(symbol)
                    if _redis_pos in ('MM', 'LT'):
                        strategy_prefix = _redis_pos
            except Exception:
                pass
            # Also try to extract engine from tag
            if 'LT' in clean_tag:
                strategy_prefix = "LT"
            if 'PA' in clean_tag or 'PAT' in clean_tag:
                engine_prefix = "PA"
            elif 'AN' in clean_tag or 'ADDNEWPOS' in clean_tag:
                engine_prefix = "AN"
            elif 'KB' in clean_tag or 'KARBOTU' in clean_tag:
                engine_prefix = "KB"
            elif 'TRIM' in clean_tag:
                engine_prefix = "TRIM"
        else:
            # Non-zero befday: determine from tag content
            if 'LT' in clean_tag and 'MM' not in clean_tag:
                strategy_prefix = "LT"
            elif 'MM' in clean_tag:
                strategy_prefix = "MM"
            # Extract engine
            if 'TRIM' in clean_tag:
                engine_prefix = "TRIM"
            elif 'KB' in clean_tag or 'KARBOTU' in clean_tag:
                engine_prefix = "KB"
            elif 'PA' in clean_tag or 'PAT' in clean_tag:
                engine_prefix = "PA"
            elif 'AN' in clean_tag or 'ADDNEWPOS' in clean_tag:
                engine_prefix = "AN"
        
        if is_long:
            if current > befday and potential > befday:
                tag_type = "INC"
                full_tag = f"{strategy_prefix}_{engine_prefix}_LONG_INC"
            elif current < befday and potential < befday:
                tag_type = "DEC"
                full_tag = f"{strategy_prefix}_{engine_prefix}_LONG_DEC"
            else:
                tag_type = "UNKNOWN"
                full_tag = f"{strategy_prefix}_{engine_prefix}_LONG_UNKNOWN"
        elif is_short:
            if current < befday and potential < befday:
                tag_type = "INC"
                full_tag = f"{strategy_prefix}_{engine_prefix}_SHORT_INC"
            elif current > befday and potential > befday:
                tag_type = "DEC"
                full_tag = f"{strategy_prefix}_{engine_prefix}_SHORT_DEC"
            else:
                tag_type = "UNKNOWN"
                full_tag = f"{strategy_prefix}_{engine_prefix}_SHORT_UNKNOWN"
        else:
            tag_type = "UNKNOWN"
            full_tag = "FLAT_UNKNOWN"
        
        if tag_type == "UNKNOWN":
            logger.warning(f"[RevnBookCheck] {symbol} Could not determine REV scenario (Bef:{befday}, Cur:{current}, Pot:{potential})")
            return
        
        logger.info(f"[RevnBookCheck] {symbol} REV scenario: {full_tag} ({'LONG' if is_long else 'SHORT'} {tag_type})")
        
        # ═══════════════════════════════════════════════════════════════════
        # FILL PRICE LOOKUP — Find the price of the fill that CAUSED the gap
        # ═══════════════════════════════════════════════════════════════════
        # gap > 0: position decreased (SELL happened) → need SELL fill price
        # gap < 0: position increased (BUY happened)  → need BUY fill price
        expected_original_action = 'SELL' if gap > 0 else 'BUY'
        fill_action_from_event = fill.get('action', '').upper()
        
        if fill_action_from_event == expected_original_action:
            # Trigger fill IS the gap-causing fill — use its price directly
            fill_price = fill.get('price', 0.0)
            logger.info(
                f"[RevnBookCheck] {symbol} Fill price: trigger fill matches "
                f"({fill_action_from_event} @ ${fill_price:.2f})"
            )
        else:
            # Trigger fill is on the WRONG side (e.g., BUY came but SELL price needed)
            # Look up the actual gap-causing fill from fill history
            fill_price = None
            try:
                from app.terminals.rev_recovery_service import get_rev_recovery_service
                _recovery_svc = get_rev_recovery_service()
                fill_result = await _recovery_svc._get_last_fill_price(
                    symbol, required_action=expected_original_action
                )
                if fill_result:
                    fill_price = fill_result['price']
                    logger.info(
                        f"[RevnBookCheck] {symbol} Fill price lookup: found "
                        f"{fill_result['action']} @ ${fill_price:.2f} "
                        f"(source: {fill_result['source']})"
                    )
            except Exception as e:
                logger.warning(f"[RevnBookCheck] {symbol} Fill price lookup failed: {e}")
            
            if not fill_price:
                # Fallback: use current market price from snapshot
                fill_price = float(getattr(snap, 'current_price', 0) or 0)
                if fill_price > 0:
                    logger.info(
                        f"[RevnBookCheck] {symbol} Using snapshot price as fallback: "
                        f"${fill_price:.2f}"
                    )
            
            if not fill_price or fill_price <= 0:
                # Last resort: use the trigger fill price
                fill_price = fill.get('price', 0.0)
                logger.warning(
                    f"[RevnBookCheck] {symbol} No {expected_original_action} fill found, "
                    f"using trigger fill price: ${fill_price:.2f}"
                )
        
        # Reconstruct a pseudo-fill event for the engine
        # The tag will be transformed by revorder_engine: INC→DEC or DEC→INC
        pseudo_fill = {
            'symbol': symbol,
            'action': 'BUY' if rev_action == 'SELL' else 'SELL',  # The fill that caused the gap
            'qty': abs(gap),
            'price': fill_price,
            'tag': full_tag,  # 8-tag format (e.g., LT_LONG_INC)
            'order_id': fill.get('order_id', '')
        }
        
        # Get L1 data
        l1_data = await self._get_l1_data(symbol)
        
        # Calculate REV order
        rev_order = self.rev_engine.calculate_rev_order(pseudo_fill, l1_data)
        
        if rev_order:
            if queue_for_later:
                # ═══════════════════════════════════════════════════════════════
                # CROSS-ACCOUNT FILL: Queue REV order for later execution
                # DualProcessRunner will pop and send when switching to this account
                # ═══════════════════════════════════════════════════════════════
                try:
                    from app.terminals.dual_account_rev_service import get_dual_account_rev_service
                    rev_service = get_dual_account_rev_service()
                    
                    # Enrich rev_order with account info and fill price
                    rev_order['account_id'] = active_account
                    rev_order['fill_price'] = fill.get('price', 0)
                    rev_order['fill_time'] = fill.get('timestamp', '')
                    rev_order['cross_account_origin'] = True
                    
                    queued = rev_service.queue_rev_orders(active_account, [rev_order])
                    if queued > 0:
                        await self._log_rev_order(fill, rev_order)
                        logger.info(
                            f"[RevnBookCheck] 📤 CROSS-ACCOUNT REV queued for {active_account}: "
                            f"{rev_order['tag']} {rev_order['action']} {rev_order['qty']} "
                            f"{rev_order['symbol']} @ ${rev_order['price']:.2f}"
                        )
                    else:
                        logger.warning(f"[RevnBookCheck] ⚠️ Cross-account REV queue returned 0 for {symbol}")
                except Exception as e:
                    logger.error(f"[RevnBookCheck] Cross-account REV queue error for {symbol}: {e}", exc_info=True)
            else:
                # NORMAL PATH: Place REV order directly
                success = await self._place_rev_order(rev_order)
                
                if success:
                    # Log to Redis
                    await self._log_rev_order(fill, rev_order)
                    
                    logger.info(
                        f"[RevnBookCheck] ✓ {rev_order['method']} REV placed: {rev_order['tag']} "
                        f"{rev_order['action']} {rev_order['qty']} @ ${rev_order['price']:.2f}"
                    )
                else:
                    logger.error(f"[RevnBookCheck] ✗ Failed to place REV order for {symbol}")
    
    # ===================
    # Redis Integration
    # ===================
    
    def _init_redis(self):
        """Initialize Redis client"""
        try:
            from app.core.redis_client import get_redis_client
            self.redis_client = get_redis_client()
            logger.info("[RevnBookCheck] Redis client initialized")
        except Exception as e:
            logger.error(f"[RevnBookCheck] Redis init error: {e}", exc_info=True)
            self.redis_client = None
    
    def _normalize_account(self, raw: str) -> str:
        """HAMMER_PRO → HAMPRO; diğerleri aynı."""
        if not raw:
            return raw
        s = (raw.decode() if isinstance(raw, bytes) else raw).strip()
        if s == "HAMMER_PRO":
            return "HAMPRO"
        return s

    async def _get_active_account_from_redis(self) -> Optional[str]:
        """
        Açık hesap = gerçekte aktif olan hesap.
        
        Öncelik sırası (CRITICAL: recovery service de aynı sırayı kullanır):
        1. psfalgo:recovery:account_open → Connect API ile açılan hesap (en güvenilir)
        2. psfalgo:xnl:running_account → XNL Engine şu anda bu hesap için çalışıyor
        3. psfalgo:account_mode → UI'da seçili mod
        
        NEDEN recovery:account_open birinci?
        - Connect API gerçekten hesabı açar, bu key sadece aktif hesap için set edilir
        - XNL running hesap ile UI hesabı farklı olabilir; recovery:account_open her zaman doğru
        """
        try:
            if not self.redis_client:
                return None
            # CRITICAL: Use .sync.get() for consistency
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            
            # PRIORITY 1: Connect API ile açılan hesap (en güvenilir)
            open_raw = redis_sync.get("psfalgo:recovery:account_open")
            if open_raw is not None:
                s = self._normalize_account(open_raw)
                if s:
                    return s
            
            # PRIORITY 2: XNL Engine hangi hesap için çalışıyor?
            xnl_running = redis_sync.get("psfalgo:xnl:running")
            if xnl_running:
                xnl_running_val = xnl_running.decode() if isinstance(xnl_running, bytes) else xnl_running
                if xnl_running_val == "1":
                    xnl_account = redis_sync.get("psfalgo:xnl:running_account")
                    if xnl_account:
                        s = self._normalize_account(xnl_account)
                        if s:
                            logger.debug(f"[RevnBookCheck] Using XNL running account: {s}")
                            return s
            
            # PRIORITY 3: UI'da seçili mod
            mode_data = redis_sync.get("psfalgo:account_mode")
            if mode_data:
                import json
                raw = mode_data.decode() if isinstance(mode_data, bytes) else mode_data
                data = json.loads(raw) if isinstance(raw, str) else {}
                m = data.get("mode", "IBKR_GUN")
                return self._normalize_account(m)
            return None
        except Exception as e:
            logger.debug(f"[RevnBookCheck] get_active_account: {e}")
            return None

    async def _get_account_mode(self) -> str:
        """Backward compat: aktif hesap yoksa IBKR_GUN döner."""
        return (await self._get_active_account_from_redis()) or "IBKR_GUN"

    async def _account_sync_loop(self):
        """
        Her 15 saniyede bir: hesap açık mı kontrol et; açık hesap = hangi hesap.
        
        DUAL PROCESS MODU: Dual Process çalışıyorsa her iki hesabı da kontrol et
        ve REV order'ları Redis queue'ya yaz. XNL Engine bu order'ları okuyup gönderir.
        
        TEK HESAP MODU: Sadece açık hesabı kontrol et ve REV order'ları doğrudan gönder.
        """
        logger.info("[RevnBookCheck] Account sync loop started (every 15s)")
        
        while self.running:
            try:
                if not self.running or not self.redis_client:
                    await asyncio.sleep(15)
                    continue
                
                # ═══════════════════════════════════════════════════════════════════
                # DUAL PROCESS CHECK: Dual Process çalışıyor mu?
                # ═══════════════════════════════════════════════════════════════════
                dual_process_running = await self._is_dual_process_running()
                
                if dual_process_running:
                    # DUAL PROCESS MODU: Her iki hesabı da kontrol et ve Redis'e yaz
                    accounts = await self._get_dual_process_accounts()
                    if accounts:
                        logger.info(f"[RevnBookCheck] 🔄 Dual Process mode: checking both accounts {accounts}")
                        await self._check_accounts_for_dual_process(accounts)
                    await asyncio.sleep(15)
                    continue
                
                # ═══════════════════════════════════════════════════════════════════
                # TEK HESAP MODU: Normal akış
                # ═══════════════════════════════════════════════════════════════════
                new_active = await self._get_active_account_from_redis()
                if new_active is None:
                    await asyncio.sleep(15)
                    continue
                    
                prev = self.account_mode
                if new_active != prev:
                    self.account_mode = new_active
                    self._recovery_ok_after = datetime.now() + timedelta(seconds=REV_ACCOUNT_SETTLE_SECONDS)
                    logger.info(f"[RevnBookCheck] Account switched: {prev or 'none'} → {new_active}. Waiting {REV_ACCOUNT_SETTLE_SECONDS}s before rev control.")
                    await self._ensure_connections()
                    
                await asyncio.sleep(15)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[RevnBookCheck] Account sync error: {e}", exc_info=True)
    
    async def _is_dual_process_running(self) -> bool:
        """
        Check if Dual Process is currently running.
        
        CRITICAL: RevnBookCheck runs in a SEPARATE PROCESS from the backend.
        So we cannot use get_dual_process_runner() which would create a new instance.
        Instead, we check Redis for Dual Process state.
        """
        try:
            if not self.redis_client:
                return False
            
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            
            # Check Redis for Dual Process state
            # DualProcessRunner writes state to Redis when it starts/stops
            state_raw = redis_sync.get("psfalgo:dual_process:state")
            if state_raw:
                import json
                state_data = json.loads(state_raw.decode() if isinstance(state_raw, bytes) else state_raw)
                is_running = state_data.get("state") == "RUNNING"
                if is_running:
                    logger.debug(f"[RevnBookCheck] Dual Process is RUNNING: accounts={state_data.get('accounts')}")
                return is_running
            return False
        except Exception as e:
            logger.debug(f"[RevnBookCheck] Dual Process state check error: {e}")
            return False
    
    async def _get_dual_process_accounts(self) -> list:
        """
        Get the two accounts configured in Dual Process.
        
        Reads from Redis since RevnBookCheck runs in a separate process.
        """
        try:
            if not self.redis_client:
                return []
            
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            state_raw = redis_sync.get("psfalgo:dual_process:state")
            if state_raw:
                import json
                state_data = json.loads(state_raw.decode() if isinstance(state_raw, bytes) else state_raw)
                accounts = state_data.get("accounts", [])
                return accounts
            return []
        except Exception as e:
            logger.debug(f"[RevnBookCheck] Get dual accounts error: {e}")
            return []
    
    async def _check_accounts_for_dual_process(self, accounts: list):
        """
        Dual Process modunda her iki hesabı da kontrol et ve REV order'ları Redis'e yaz.
        DualProcessRunner bu order'ları okuyup gönderecek.
        
        CRITICAL: Before health check, refresh Redis positions for BOTH accounts.
        Without this, accounts not currently active (e.g., IBKR_PED during HAMPRO cycle)
        have stale Redis data, causing missed REV orders.
        """
        try:
            from app.terminals.dual_account_rev_service import get_dual_account_rev_service
            rev_service = get_dual_account_rev_service()
            
            # ═══════════════════════════════════════════════════════════════
            # STEP 0: Refresh Redis positions for BOTH accounts
            # This prevents stale data (e.g., IBKR_PED written once, never updated)
            # ═══════════════════════════════════════════════════════════════
            for account_id in accounts:
                try:
                    await self._refresh_positions_in_redis(account_id)
                except Exception as e:
                    logger.debug(f"[RevnBookCheck] Position refresh for {account_id}: {e}")
            
            for account_id in accounts:
                try:
                    # Check health gaps
                    rev_orders = await rev_service.check_account_health(account_id)
                    if rev_orders:
                        queued = rev_service.queue_rev_orders(account_id, rev_orders)
                        logger.info(f"[RevnBookCheck] 📤 Queued {queued} REV orders for {account_id} (Dual Process)")
                except Exception as e:
                    logger.warning(f"[RevnBookCheck] Error checking {account_id} for Dual Process: {e}")
                    
        except Exception as e:
            logger.error(f"[RevnBookCheck] Dual Process check error: {e}")

    async def _refresh_positions_in_redis(self, account_id: str):
        """
        Refresh Redis positions cache for a specific account via backend API.
        
        This ensures positions are always current, even for accounts not
        currently running cycles (e.g., IBKR_PED during HAMPRO phase).
        
        Only refreshes if existing Redis data is older than 2 minutes.
        """
        try:
            import json as _json
            import time as _time
            
            if not self.redis_client:
                return
            
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            positions_key = f"psfalgo:positions:{account_id}"
            
            # Check current age — skip if recently updated (< 2 minutes)
            raw = redis_sync.get(positions_key)
            if raw:
                current_data = _json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                meta = current_data.get('_meta', {})
                age = _time.time() - meta.get('updated_at', 0)
                if age < 120:  # Less than 2 minutes old → still fresh
                    return
                logger.info(
                    f"[RevnBookCheck] 🔄 Refreshing stale positions for {account_id} "
                    f"(age={age:.0f}s)"
                )
            
            # Fetch fresh positions from backend API
            import asyncio
            
            def _fetch():
                import requests
                url = "http://localhost:8000/api/trading/positions"
                r = requests.get(url, params={"account_id": account_id}, timeout=10)
                r.raise_for_status()
                return r.json()
            
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, _fetch)
            positions = data.get("positions") or []
            
            if not positions:
                return
            
            # Build positions dict for Redis
            positions_dict = {}
            for p in positions:
                sym = p.get("symbol", "")
                if sym:
                    _qty = float(p.get("qty") or p.get("quantity") or 0)
                    # IMPORTANT: Use explicit None check for potential_qty
                    # because potential_qty=0 is valid (flat position) but
                    # `0 or _qty` would falsely use _qty due to Python truthiness
                    _pot = p.get("potential_qty")
                    _pot = float(_pot) if _pot is not None else _qty
                    
                    positions_dict[sym] = {
                        "symbol": sym,
                        "qty": _qty,
                        "potential_qty": _pot,
                        "befday_qty": float(p.get("befday_qty") or 0),
                        "avg_price": float(p.get("avg_price") or 0),
                        "current_price": float(p.get("current_price") or 0),
                        "unrealized_pnl": float(p.get("unrealized_pnl") or 0),
                        "strategy_type": p.get("strategy_type", "LT"),
                        "origin_type": p.get("origin_type", "OV"),
                    }
            
            positions_dict['_meta'] = {'updated_at': _time.time()}
            redis_sync.set(positions_key, _json.dumps(positions_dict), ex=3600)
            
            logger.info(
                f"[RevnBookCheck] ✅ Refreshed {len(positions_dict)-1} positions "
                f"in Redis for {account_id}"
            )
            
        except Exception as e:
            logger.debug(f"[RevnBookCheck] Position refresh failed for {account_id}: {e}")

    
    async def _subscribe_fill_events(self):
        """Monitor execution ledger for fill events"""
        if not self.redis_client:
            logger.warning("[RevnBookCheck] No Redis client, fill monitoring disabled")
            return
        
        logger.info("[RevnBookCheck] Starting fill event monitoring (Redis Stream)")
        # Only new messages — avoid reprocessing old AAPL/test fills on every startup
        last_id = '$'
        
        while self.running:
            try:
                # CRITICAL: xread is a BLOCKING sync call (up to 5s).
                # Must run in executor to avoid blocking the asyncio event loop
                # which would stall all other concurrent tasks (recovery, frontlama, etc.)
                loop = asyncio.get_running_loop()
                events = await loop.run_in_executor(
                    None,
                    lambda: self.redis_client.xread(
                        {'psfalgo:execution:ledger': last_id},
                        count=10,
                        block=5000  # 5 second timeout
                    )
                )
                
                if events:
                    for stream_name, messages in events:
                        for message_id, data in messages:
                            # Decode and process
                            fill_data = {k.decode() if isinstance(k, bytes) else k: 
                                       v.decode() if isinstance(v, bytes) else v 
                                       for k, v in data.items()}
                            
                            await self._process_fill_from_stream(fill_data)
                            
                            # Update checkpoint
                            last_id = message_id
                
            except Exception as e:
                logger.error(f"[RevnBookCheck] Stream monitoring error: {e}", exc_info=True)
                await asyncio.sleep(5)
    
    async def _process_fill_from_stream(self, data: Dict):
        """Process fill event from Redis stream
        
        DUAL PROCESS AWARENESS:
        When Dual Process is running (e.g., HAMPRO phase active), fills from the OTHER
        account (e.g., IBKR_PED) must NOT be dropped. Instead, the fill is processed
        normally and the resulting REV order is queued to Redis for execution when
        DualProcessRunner switches to that account.
        
        This preserves the fill price information which would otherwise be lost.
        """
        try:
            fill_event = {
                'symbol': str(data.get('symbol', '')),
                'action': str(data.get('action', '') or data.get('side', '')),  # IBKR+Hammer both write 'action'
                'qty': float(data.get('qty', 0)),
                'price': float(data.get('price', 0)),
                'order_id': str(data.get('order_id', '') or data.get('fill_id', '')),
                'tag': str(data.get('tag', '') or data.get('strategy_tag', '')),
                'account_id': str(data.get('account_id', ''))
            }
            
            # CRITICAL: Normalize both sides (HAMMER_PRO → HAMPRO)
            fill_account = self._normalize_account(fill_event['account_id'])
            current_mode = self.account_mode
            
            if not current_mode:
                logger.info(f"[RevnBookCheck] No active account, skipping fill from {fill_account}")
                return
            
            # ═══════════════════════════════════════════════════════════════════
            # DUAL PROCESS FILL ROUTING
            # ═══════════════════════════════════════════════════════════════════
            # target_account: which account this fill belongs to (for position lookup + REV routing)
            target_account = fill_account  # default: the account the fill came from
            is_cross_account_fill = False
            
            if fill_account != current_mode:
                # Fill is from a different account than what's currently active
                dual_process_running = await self._is_dual_process_running()
                
                if dual_process_running:
                    # DUAL PROCESS MODE: Don't drop this fill!
                    # Process it and queue the REV order for later execution
                    dual_accounts = await self._get_dual_process_accounts()
                    if fill_account in dual_accounts:
                        is_cross_account_fill = True
                        target_account = fill_account
                        logger.info(
                            f"[RevnBookCheck] 🔄 DUAL PROCESS: Cross-account fill detected! "
                            f"Fill from {fill_account} while {current_mode} is active. "
                            f"Will process and queue REV for {fill_account}."
                        )
                    else:
                        logger.info(
                            f"[RevnBookCheck] Skipping fill from {fill_account} "
                            f"(not in dual process accounts: {dual_accounts})"
                        )
                        return
                else:
                    # SINGLE ACCOUNT MODE: Skip fills from other accounts (original behavior)
                    logger.info(
                        f"[RevnBookCheck] Skipping fill from {fill_account} "
                        f"(active: {current_mode})"
                    )
                    return
            
            # Sadece hedef hesabın pozisyon/BEFDAY evrenindeki semboller için işle (Redis)
            # AAPL vb. test/alakasız fill'leri atla
            try:
                positions = await self._get_positions_for_account(target_account)
                befday_data = await self._get_befday_data_for_account(target_account)
                valid_symbols = set(p.get('symbol', '') for p in positions if p.get('symbol'))
                valid_symbols |= set(befday_data.keys()) if befday_data else set()
                sym = str(fill_event['symbol']).strip()
                if sym and sym not in valid_symbols:
                    logger.info(
                        f"[RevnBookCheck] Ignoring fill for {sym} — not in positions or BEFDAY for {target_account} "
                        f"(valid universe: {len(valid_symbols)} symbols)"
                    )
                    return
            except Exception as e:
                logger.warning(f"[RevnBookCheck] Valid-symbols check failed: {e}")
                return
            
            # Check if already has REV
            if await self._check_existing_rev(fill_event['symbol'], fill_event['order_id']):
                logger.debug(f"[RevnBookCheck] REV already exists for {fill_event['symbol']}")
                return
            
            # Process fill
            logger.info(
                f"[RevnBookCheck] New fill: {fill_event['symbol']} "
                f"{fill_event['action']} {fill_event['qty']} @ ${fill_event['price']:.2f}"
                f"{' [CROSS-ACCOUNT→' + target_account + ']' if is_cross_account_fill else ''}"
            )
            
            await self._process_fill(fill_event, target_account=target_account, queue_for_later=is_cross_account_fill)
            
            # ── MM EXIT GUARD: Notify with actual fill price ──
            # fill_tag_handler also notifies but without fill_price.
            # Here we have the actual price from the stream, so update the guard.
            try:
                fill_tag = str(fill_event.get('tag', '')).upper()
                fill_source = str(data.get('source', '') or data.get('engine', '')).upper()
                is_mm_fill = (
                    'GREATEST_MM' in fill_source
                    or 'MM_ENGINE' in fill_source
                    or (fill_tag.startswith('MM_MM_') and 'INC' in fill_tag)
                )
                if is_mm_fill and fill_event['price'] > 0 and fill_event['qty'] >= 200:
                    from app.mm.mm_exit_guard import get_mm_exit_guard
                    guard = get_mm_exit_guard()
                    guard.on_mm_fill(
                        symbol=fill_event['symbol'],
                        action=fill_event['action'],
                        fill_price=fill_event['price'],
                        fill_qty=int(fill_event['qty']),
                        account_id=target_account,
                        tag=fill_event.get('tag', ''),
                        source=fill_source,
                    )
            except Exception as guard_err:
                logger.debug(f"[RevnBookCheck] MM Exit Guard notify error: {guard_err}")
            
        except Exception as e:
            logger.error(f"[RevnBookCheck] Fill processing error: {e}", exc_info=True)
    
    async def _check_existing_rev(self, symbol: str, fill_id: str) -> bool:
        """Check if REV already exists for this fill"""
        try:
            if not self.redis_client:
                return False
            
            key = f"psfalgo:revorders:active:{symbol}"
            data = self.redis_client.get(key)
            
            if data:
                import json
                rev_data = json.loads(data)
                if rev_data.get('original_fill', {}).get('order_id') == fill_id:
                    return True
            
            return False
        except Exception as e:
            logger.debug(f"[RevnBookCheck] REV check error: {e}")
            return False
    
    # ===================
    # Data Fetching
    # ===================
    
    async def _get_befday_data(self) -> Dict[str, float]:
        """Get BEFDAY position quantities from Redis.
        
        Multi-source lookup (same priority as PositionSnapshotAPI._load_befday_map):
        1. psfalgo:befday:positions:{account}  → Dedicated BEFDAY key (list format)
        2. psfalgo:positions:{account}          → Unified positions key (dict format, has befday_qty)
        
        Both sources are checked; first non-empty result wins.
        """
        try:
            if not self.redis_client or not self.account_mode:
                return {}
            
            import json
            
            # CRITICAL: Use .sync.get() for consistency
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            
            # ═══════════════════════════════════════════════════════════════
            # SOURCE 1: Dedicated BEFDAY key (list format — same as _load_befday_map reads)
            # This key is populated by befday_tracker and is the authoritative source
            # ═══════════════════════════════════════════════════════════════
            befday_key = f"psfalgo:befday:positions:{self.account_mode}"
            befday_raw = redis_sync.get(befday_key)
            if befday_raw:
                raw = befday_raw.decode() if isinstance(befday_raw, bytes) else befday_raw
                befday_data = json.loads(raw)
                befday_map = {}
                if isinstance(befday_data, list):
                    for item in befday_data:
                        sym = str(item.get('symbol', '')).strip()
                        qty = float(item.get('qty', 0) or 0)
                        side = str(item.get('side', '')).strip().lower()
                        full_tax = str(item.get('full_taxonomy', '')).upper()
                        # BEFDAY: short must always be negative
                        if qty > 0 and (side == 'short' or 'SHORT' in full_tax):
                            qty = -qty
                        if sym and qty != 0:
                            befday_map[sym] = qty
                elif isinstance(befday_data, dict):
                    for sym, val in befday_data.items():
                        if isinstance(val, dict):
                            qty = float(val.get('quantity', val.get('qty', 0)) or 0)
                        else:
                            qty = float(val or 0)
                        if sym and qty != 0:
                            befday_map[sym] = qty
                if befday_map:
                    logger.debug(f"[RevnBookCheck] Loaded {len(befday_map)} BEFDAY entries from {befday_key}")
                    return befday_map
            
            # ═══════════════════════════════════════════════════════════════
            # SOURCE 2: Unified positions key (dict format — has befday_qty field)
            # ═══════════════════════════════════════════════════════════════
            positions_key = f"psfalgo:positions:{self.account_mode}"
            data = redis_sync.get(positions_key)
            
            if data:
                raw = data.decode() if isinstance(data, bytes) else data
                positions_dict = json.loads(raw)
                # Extract befday_qty from positions dict
                befday_map = {}
                for sym, pos in positions_dict.items():
                    if sym and sym != '_meta' and isinstance(pos, dict):
                        befday_qty = float(pos.get('befday_qty', 0) or 0)
                        if befday_qty != 0:
                            befday_map[sym] = befday_qty
                if befday_map:
                    logger.debug(f"[RevnBookCheck] Loaded {len(befday_map)} BEFDAY entries from {positions_key}")
                    return befday_map
            
            logger.debug(f"[RevnBookCheck] No BEFDAY data found for {self.account_mode} in Redis")
            return {}
        
        except Exception as e:
            logger.error(f"[RevnBookCheck] BEFDAY load error: {e}")
            return {}
    
    async def _get_positions(self) -> List[Dict]:
        """Get current positions from Redis (aktif hesap = self.account_mode).
        
        Staleness Guard: Warns if data is >10 minutes old.
        Strips internal _meta key before returning.
        """
        try:
            if not self.redis_client or not self.account_mode:
                return []
            
            import json
            import time as _time
            
            key = f"psfalgo:positions:{self.account_mode}"
            # CRITICAL: Use .sync.get() for consistency
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            data = redis_sync.get(key)
            
            if data:
                raw = data.decode() if isinstance(data, bytes) else data
                positions_dict = json.loads(raw)
                
                # ── STALENESS CHECK ──
                meta = positions_dict.pop('_meta', None)
                if meta and isinstance(meta, dict):
                    updated_at = meta.get('updated_at', 0)
                    age_sec = _time.time() - updated_at
                    if age_sec > 600:  # 10 minutes
                        logger.warning(
                            f"[RevnBookCheck] ⚠️ Positions data is STALE "
                            f"({age_sec/60:.1f}m old) for {self.account_mode}"
                        )
                
                # CRITICAL: Inject 'symbol' from dict key if missing
                result = []
                for sym, pos_data in positions_dict.items():
                    if isinstance(pos_data, dict):
                        if 'symbol' not in pos_data:
                            pos_data['symbol'] = sym
                        result.append(pos_data)
                return result
            else:
                logger.debug(f"[RevnBookCheck] No positions for {self.account_mode}")
                return []
        
        except Exception as e:
            logger.error(f"[RevnBookCheck] Positions load error: {e}")
            return []
    
    async def _get_positions_for_account(self, account_id: str) -> List[Dict]:
        """Get current positions from Redis for a specific account.
        
        Used by cross-account fill processing in Dual Process mode.
        Falls back to self.account_mode if account_id matches.
        """
        try:
            if not self.redis_client or not account_id:
                return []
            
            import json
            
            key = f"psfalgo:positions:{account_id}"
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            data = redis_sync.get(key)
            
            if data:
                raw = data.decode() if isinstance(data, bytes) else data
                positions_dict = json.loads(raw)
                result = []
                for sym, pos_data in positions_dict.items():
                    if sym != '_meta' and isinstance(pos_data, dict):
                        if 'symbol' not in pos_data:
                            pos_data['symbol'] = sym
                        result.append(pos_data)
                return result
            else:
                logger.debug(f"[RevnBookCheck] No positions for {account_id}")
                return []
        
        except Exception as e:
            logger.error(f"[RevnBookCheck] Positions load error for {account_id}: {e}")
            return []
    
    async def _get_befday_data_for_account(self, account_id: str) -> Dict[str, float]:
        """Get BEFDAY position quantities from Redis for a specific account.
        
        Used by cross-account fill processing in Dual Process mode.
        Same multi-source lookup as _get_befday_data but with explicit account_id.
        """
        try:
            if not self.redis_client or not account_id:
                return {}
            
            import json
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            
            # SOURCE 1: Dedicated BEFDAY key
            befday_key = f"psfalgo:befday:positions:{account_id}"
            befday_raw = redis_sync.get(befday_key)
            if befday_raw:
                raw = befday_raw.decode() if isinstance(befday_raw, bytes) else befday_raw
                befday_data = json.loads(raw)
                befday_map = {}
                if isinstance(befday_data, list):
                    for item in befday_data:
                        sym = str(item.get('symbol', '')).strip()
                        qty = float(item.get('qty', 0) or 0)
                        side = str(item.get('side', '')).strip().lower()
                        full_tax = str(item.get('full_taxonomy', '')).upper()
                        if qty > 0 and (side == 'short' or 'SHORT' in full_tax):
                            qty = -qty
                        if sym and qty != 0:
                            befday_map[sym] = qty
                elif isinstance(befday_data, dict):
                    for sym, val in befday_data.items():
                        if isinstance(val, dict):
                            qty = float(val.get('quantity', val.get('qty', 0)) or 0)
                        else:
                            qty = float(val or 0)
                        if sym and qty != 0:
                            befday_map[sym] = qty
                if befday_map:
                    return befday_map
            
            # SOURCE 2: Unified positions key
            positions_key = f"psfalgo:positions:{account_id}"
            data = redis_sync.get(positions_key)
            if data:
                raw = data.decode() if isinstance(data, bytes) else data
                positions_dict = json.loads(raw)
                befday_map = {}
                for sym, pos in positions_dict.items():
                    if sym and sym != '_meta' and isinstance(pos, dict):
                        befday_qty = float(pos.get('befday_qty', 0) or 0)
                        if befday_qty != 0:
                            befday_map[sym] = befday_qty
                if befday_map:
                    return befday_map
            
            return {}
        
        except Exception as e:
            logger.error(f"[RevnBookCheck] BEFDAY load error for {account_id}: {e}")
            return {}
    
    async def _get_open_orders(self) -> List[Dict]:
        """Get open orders: CRITICAL - Read from Redis (backend writes here)
        
        Staleness Guard: Returns empty list if data is >5 minutes old.
        Handles both new wrapped format ({'orders': [...], '_meta': {...}})
        and legacy plain list format for backward compatibility.
        """
        account = self.account_mode or ""
        if not account:
            return []
        
        # CRITICAL: Read from Redis (backend writes here)
        try:
            import json
            import time as _time
            if self.redis_client and getattr(self.redis_client, 'sync', None):
                orders_key = f"psfalgo:open_orders:{account}"
                raw_orders = self.redis_client.sync.get(orders_key)
                if raw_orders:
                    parsed = json.loads(raw_orders.decode() if isinstance(raw_orders, bytes) else raw_orders)
                    
                    # Handle wrapped format vs legacy list
                    if isinstance(parsed, dict) and 'orders' in parsed:
                        # New format: {'orders': [...], '_meta': {'updated_at': ...}}
                        orders = parsed.get('orders', [])
                        meta = parsed.get('_meta', {})
                        updated_at = meta.get('updated_at', 0)
                        age_sec = _time.time() - updated_at if updated_at else 999999
                        
                        if age_sec > 300:  # 5 minutes — orders are volatile
                            logger.warning(
                                f"[RevnBookCheck] ⏰ Open orders data is STALE "
                                f"({age_sec/60:.1f}m old) for {account}, returning empty"
                            )
                            return []
                    elif isinstance(parsed, list):
                        # Legacy plain list format (no staleness info)
                        orders = parsed
                    else:
                        logger.warning(f"[RevnBookCheck] Unexpected open_orders format: {type(parsed)}")
                        return []
                    
                    if orders:
                        logger.info(f"[RevnBookCheck] ✅ Read {len(orders)} open orders from Redis {orders_key}")
                        return orders
                    else:
                        logger.debug(f"[RevnBookCheck] Redis {orders_key} exists but empty")
                else:
                    logger.debug(f"[RevnBookCheck] Redis {orders_key} not found (backend may not have written yet)")
        except Exception as e:
            logger.warning(f"[RevnBookCheck] Redis read open orders failed: {e}")
        
        # Fallback: empty list (backend will write to Redis soon)
        return []
    
    async def _get_new_fills(self, since: datetime) -> List[Dict]:
        """Get fills since timestamp - handled by stream monitoring"""
        # This method is replaced by Redis stream monitoring
        # Keeping for compatibility
        return []
    
    async def _get_l1_data(self, symbol: str) -> Dict[str, Any]:
        """Get L1 market data from Redis (market:l1:{symbol} then fallback market_data:snapshot:{symbol})"""
        try:
            if not self.redis_client:
                return {'bid': 0.0, 'ask': 0.0, 'spread': 0.0}
            import json
            
            # CRITICAL: Use .sync.get() for consistency
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            
            # Prefer market:l1 (written by snapshot_scheduler / l1_feed_worker every 15s when backend runs)
            key = f"market:l1:{symbol}"
            data = redis_sync.get(key)
            if data:
                raw = data.decode() if isinstance(data, bytes) else data
                l1 = json.loads(raw)
                bid = float(l1.get('bid', 0))
                ask = float(l1.get('ask', 0))
                spread = float(l1.get('spread', 0))
                if spread == 0 and bid and ask:
                    spread = ask - bid
                if bid or ask:
                    return {'bid': bid, 'ask': ask, 'spread': spread}
            # Fallback: backend snapshot (market_data:snapshot:{symbol})
            snap_key = f"market_data:snapshot:{symbol}"
            snap_data = redis_sync.get(snap_key)
            if snap_data:
                raw = snap_data.decode() if isinstance(snap_data, bytes) else snap_data
                snap = json.loads(raw)
                bid = float(snap.get('bid', 0))
                ask = float(snap.get('ask', 0))
                spread = (ask - bid) if (bid and ask) else 0.0
                if bid or ask:
                    return {'bid': bid, 'ask': ask, 'spread': spread}
            return {'bid': 0.0, 'ask': 0.0, 'spread': 0.0}
        except Exception as e:
            logger.error(f"[RevnBookCheck] L1 data error for {symbol}: {e}")
            return {'bid': 0.0, 'ask': 0.0, 'spread': 0.0}
    
    def _is_xnl_running(self) -> bool:
        """REV order sadece XNL run edildiğinde çalışır; terminaller bu key'e bakacak."""
        try:
            if not self.redis_client:
                return False
            # CRITICAL: Use .sync.get() for consistency
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            val = redis_sync.get("psfalgo:xnl:running")
            if val is None:
                return False
            s = (val.decode() if isinstance(val, bytes) else val) or ""
            return str(s).strip() == "1"
        except Exception:
            return False

    def _xnl_running_account(self) -> Optional[str]:
        """XNL şu an hangi hesap için run ediyor (psfalgo:xnl:running_account). HAMPRO/IBKR_PED/IBKR_GUN."""
        try:
            if not self.redis_client:
                return None
            # CRITICAL: Use .sync.get() for consistency
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            val = redis_sync.get("psfalgo:xnl:running_account")
            if val is None:
                return None
            s = (val.decode() if isinstance(val, bytes) else val) or ""
            s = str(s).strip()
            return s if s else None
        except Exception:
            return None

    def _account_matches_xnl(self) -> bool:
        """Aktif hesap (self.account_mode) ile XNL'in run ettiği hesap (running_account) aynı mı? REV sadece o hesapta atılır."""
        if not self._is_xnl_running():
            return False
        running_acc = self._xnl_running_account()
        if not running_acc:
            return True  # Eski davranış: account yoksa yine de izin ver (geriye uyum)
        my_acc = (self.account_mode or "").strip().upper()
        run_acc = (running_acc or "").strip().upper()
        if my_acc == "HAMMER_PRO":
            my_acc = "HAMPRO"
        if run_acc == "HAMMER_PRO":
            run_acc = "HAMPRO"
        return my_acc == run_acc

    async def _is_hard_risk_for_account(self, account_id: str) -> bool:
        """Hard risk modunda REV saved/reload (INC) atlanır."""
        try:
            import os
            base = os.environ.get("QUANT_ENGINE_URL", "http://localhost:8000")
            url = f"{base}/api/psfalgo/hard-risk-status"
            import asyncio
            def _get():
                try:
                    import urllib.request
                    req = urllib.request.Request(f"{url}?account_id={account_id}", method="GET")
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        import json
                        data = json.loads(resp.read().decode())
                        return data.get("hard_risk", False)
                except Exception:
                    return False
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _get)
        except Exception as e:
            logger.debug(f"[RevnBookCheck] hard-risk check: {e}")
            return False

    async def _place_rev_order(self, rev_order: Dict) -> bool:
        """
        Place REV order via Redis Queue (NEW PATTERN - no HTTP timeout).
        
        REV sadece XNL run edildiğinde çalışır (psfalgo:xnl:running=1).
        Hard risk modunda REV saved/reload (_INC) atlanır; sadece take profit (_DEC) gider.
        
        Flow:
        1. Check XNL running; 2. If REV is INC and hard risk → skip
        3. Write order to Redis queue (psfalgo:orders:pending)
        4. Backend OrderQueueWorker processes it
        
        Hesap moduna göre: IBKR_PED/IBKR_GUN → Gateway; HAMPRO → Hammer Pro mantığı.
        """
        try:
            import uuid
            import json
            from datetime import datetime

            if not self.redis_client:
                logger.error("[RevnBookCheck] No Redis client, cannot queue order")
                return False

            # REV order sadece XNL run edildiğinde ve aktif hesap = XNL'in run ettiği hesap
            if not self._is_xnl_running():
                logger.info("[RevnBookCheck] XNL not running, REV placement skipped")
                return False
            if not self._account_matches_xnl():
                running_acc = self._xnl_running_account() or "?"
                logger.info(
                    f"[RevnBookCheck] XNL running for {running_acc}, active account is {self.account_mode or '?'}; "
                    "REV placement skipped (only place REV for the account XNL is running for)"
                )
                return False

            account_id = self.account_mode or "IBKR_GUN"  # HAMPRO, IBKR_PED, IBKR_GUN

            # Hard risk: RELOAD orders (position-increasing) are blocked.
            # TP orders (position-decreasing, taking profit) are always allowed.
            # rev_type field: "RELOAD" or "TP" (set by RevOrderEngine)
            rev_type_check = (rev_order.get("rev_type") or "").upper()
            rev_tag_check = (rev_order.get("tag") or "").upper()
            is_reload = rev_type_check == "RELOAD" or rev_tag_check.endswith("_INC")
            if is_reload:
                hard = await self._is_hard_risk_for_account(account_id)
                if hard:
                    logger.info(
                        f"[RevnBookCheck] Hard risk mode, RELOAD (position-increasing) skipped: "
                        f"{rev_order.get('symbol')} {rev_tag_check} (rev_type={rev_type_check})"
                    )
                    return False
            
            # ══════════════════════════════════════════════════════════════
            # 🔄 CANCEL-REFRESH: Clear stale REV before REVERSE GUARD
            # Same pattern as dual_process_runner._send_pending_rev_orders
            # Ensures fresh REV at current price replaces stale one
            # ══════════════════════════════════════════════════════════════
            from app.psfalgo.reverse_guard import check_reverse_guard, clear_pending_rev_for_symbol
            
            symbol = rev_order.get('symbol', '')
            cleared = clear_pending_rev_for_symbol(symbol, account_id)
            if cleared > 0:
                logger.info(
                    f"[RevnBookCheck] 🔄 REV REFRESH: cleared {cleared} stale entries "
                    f"for {symbol} on {account_id}"
                )
            
            # ── REVERSE GUARD: Check open orders + position before queuing ──
            rg_ok, rg_qty, rg_rsn = check_reverse_guard(
                symbol=symbol,
                action=rev_order.get('action', ''),
                quantity=float(rev_order.get('qty', 0)),
                tag=rev_order.get('tag', ''),
                account_id=account_id,
            )
            if not rg_ok:
                logger.warning(
                    f"[RevnBookCheck] 🛡️ REVERSE GUARD BLOCKED: "
                    f"{rev_order.get('symbol')} {rev_order.get('action')} "
                    f"{rev_order.get('qty')} | {rg_rsn}"
                )
                return False
            if rg_qty != float(rev_order.get('qty', 0)):
                logger.warning(
                    f"[RevnBookCheck] 🛡️ REVERSE GUARD TRIMMED: "
                    f"{rev_order.get('symbol')} {rev_order.get('action')} "
                    f"{rev_order.get('qty')} → {rg_qty} | {rg_rsn}"
                )
                rev_order['qty'] = rg_qty
            
            # Generate unique order ID
            order_id = str(uuid.uuid4())
            
            # Prepare order data for Redis queue
            order_data = {
                "order_id": order_id,
                "symbol": rev_order["symbol"],
                "action": rev_order["action"],  # BUY/SELL
                "qty": int(rev_order["qty"]),
                "price": float(rev_order["price"]),
                "order_type": "LIMIT",
                "account_id": account_id,
                "source": "REVNBOOK",
                "strategy_tag": rev_order.get("tag", "REV_TP"),
                "timestamp": datetime.now().isoformat(),
                "rev_order_metadata": {
                    "method": rev_order.get("method", "UNKNOWN"),
                    "original_fill_price": rev_order.get("fill_price"),
                    "original_fill_id": rev_order.get("original_fill_id", "")
                }
            }
            
            # Write to Redis queue (LPUSH - left push, worker uses BLPOP)
            queue_key = "psfalgo:orders:pending"
            if hasattr(self.redis_client, 'lpush'):
                self.redis_client.lpush(queue_key, json.dumps(order_data))
            elif hasattr(self.redis_client, 'sync'):
                self.redis_client.sync.lpush(queue_key, json.dumps(order_data))
            else:
                logger.error("[RevnBookCheck] Redis client does not support lpush")
                return False
            
            # Set initial status
            status_key = f"psfalgo:orders:status:{order_id}"
            initial_status = {
                "status": "QUEUED",
                "message": "Order queued for processing",
                "timestamp": datetime.now().isoformat(),
                "symbol": rev_order["symbol"],
                "action": rev_order["action"],
                "qty": int(rev_order["qty"]),
                "price": float(rev_order["price"]),
                "account_id": account_id
            }
            self.redis_client.setex(status_key, 3600, json.dumps(initial_status))  # 1 hour TTL
            
            # Store order_id in rev_order for tracking
            rev_order["order_id"] = order_id
            await self._save_rev_order_to_redis(rev_order)
            
            logger.info(
                f"[RevnBookCheck] ✅ Order queued: {order_id} | "
                f"{rev_order['action']} {rev_order['qty']} {rev_order['symbol']} @ {rev_order['price']:.2f} | "
                f"Account: {account_id}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"[RevnBookCheck] Order queue error: {e}", exc_info=True)
            return False
    
    async def _save_rev_order_to_redis(self, rev_order: Dict):
        """Save REV order to Redis for tracking"""
        try:
            if not self.redis_client:
                return
            
            import json
            
            key = f"psfalgo:revorders:active:{rev_order['symbol']}"
            
            data = {
                'symbol': rev_order['symbol'],
                'original_fill': {
                    'order_id': rev_order.get('original_fill_id', ''),
                    'action': 'SELL' if rev_order['action'] == 'BUY' else 'BUY',  # Original fill = opposite of REV
                    'qty': rev_order['qty'],
                    'price': rev_order['fill_price'],
                    'timestamp': datetime.now().isoformat()
                },
                'rev_order': {
                    'order_id': rev_order.get('order_id', ''),
                    'action': rev_order['action'],
                    'qty': rev_order['qty'],
                    'price': rev_order['price'],
                    'tag': rev_order['tag'],
                    'timestamp': datetime.now().isoformat(),
                    'status': 'PENDING',
                    'account_id': self.account_mode,
                    'method': rev_order.get('method', 'UNKNOWN')
                }
            }
            
            # Save with 24 hour TTL (RedisClient uses set(key, value, ex=ttl))
            self.redis_client.set(key, json.dumps(data), ex=86400)
            
            logger.debug(f"[RevnBookCheck] Saved REV to Redis: {key}")
        
        except Exception as e:
            logger.error(f"[RevnBookCheck] Redis save error: {e}")
    
    async def _log_rev_order(self, fill: Dict, rev_order: Dict):
        """Log REV order creation"""
        method_desc = rev_order.get('method', 'UNKNOWN')
        # Map method to clearer description if it's orderbook level
        if "LEVEL_" in method_desc:
            level = rev_order.get('level', '?')
            action_dir = "Bid" if rev_order['action'] == 'BUY' else "Ask"
            method_desc = f"{rev_order['action']} in front of {action_dir} Level {level} (Öncelik Alındı)"
            
        fill_price = rev_order.get('fill_price', 0)
        rev_price = rev_order.get('price', 0)
        gap = abs(rev_price - fill_price) if fill_price and rev_price else 0
        
        logger.info(
            f"[RevnBookCheck] ✓ {method_desc}: {rev_order['symbol']} "
            f"{rev_order['action']} {rev_order['qty']} @ ${rev_order['price']:.2f} "
            f"(Fill: ${fill_price:.2f}, Gap: ${gap:.2f})"
        )
    
    # ═══════════════════════════════════════════════════════════════════════
    # FRONTLAMA HELPER METHODS - Open Orders & L1 Data
    # ═══════════════════════════════════════════════════════════════════════
    # NOTE: Frontlama uses the SAME _get_open_orders (line ~837) and 
    # _get_l1_data (line ~870) as REV/Recovery. No duplicate definitions.
    # The canonical methods support both use cases:
    # - _get_open_orders: Redis → fallback empty list (OrderController 
    #   is used by XNL Engine directly, not by this terminal)
    # - _get_l1_data: market:l1 → market_data:snapshot fallback
    
    # ═══════════════════════════════════════════════════════════════════════
    # FRONTLAMA ENGINE - Runs every 60 seconds
    # ═══════════════════════════════════════════════════════════════════════
    
    def _is_execution_ready(self) -> bool:
        """
        Check if execution infrastructure is ready for order modifications.
        
        Returns True ONLY if:
        1. Account mode is set
        2. Execution provider (Hammer/IBKR) is connected
        3. Backend API is reachable (quick health check)
        
        This prevents the timeout cascade when system is starting up
        or provider connections haven't been established yet.
        """
        try:
            # Check 1: Account mode must be set
            if not self.account_mode:
                return False
            
            # Check 2: Execution provider must be connected
            from app.execution.execution_router import get_execution_router
            from app.trading.trading_account_context import TradingAccountMode
            
            router = get_execution_router()
            if not router:
                return False
            
            # Map account to mode
            if self.account_mode in ("HAMPRO", "HAMMER_PRO"):
                mode_enum = TradingAccountMode.HAMPRO
            elif self.account_mode == "IBKR_PED":
                mode_enum = TradingAccountMode.IBKR_PED
            elif self.account_mode == "IBKR_GUN":
                mode_enum = TradingAccountMode.IBKR_GUN
            else:
                return False
            
            provider = router.providers.get(mode_enum)
            if not provider:
                return False
            
            # Check provider status (connected?)
            from app.execution.execution_provider import ExecutionProviderStatus
            status = provider.get_status()
            if status != ExecutionProviderStatus.CONNECTED:
                return False
            
            return True
            
        except Exception:
            return False
    
    def _is_backend_reachable(self) -> bool:
        """
        Quick health check: is localhost:8000 responding?
        Uses a very short timeout (1s) to avoid blocking.
        Only used as final fallback check.
        """
        try:
            import requests
            resp = requests.get("http://localhost:8000/health", timeout=1)
            return resp.status_code == 200
        except Exception:
            return False
    
    async def _frontlama_loop(self):
        """
        Main frontlama loop - runs every 60 seconds.
        
        Evaluates ALL active orders and determines if any can be fronted
        based on valid truth ticks and sacrifice limits.
        
        SAFETY: Checks execution readiness before each cycle.
        If provider is not connected, skips the entire cycle gracefully.
        """
        logger.info(f"[Frontlama] 🚀 Starting frontlama loop (interval: {self.frontlama_interval}s)")
        
        while self.running:
            try:
                # ── READINESS CHECK: Skip cycle if execution infra not ready ──
                if not self._is_execution_ready():
                    logger.debug(f"[Frontlama] ⏸️ Execution not ready (provider not connected), skipping cycle")
                    await asyncio.sleep(self.frontlama_interval)
                    continue
                
                await self._run_frontlama_cycle()
                await asyncio.sleep(self.frontlama_interval)
            except Exception as e:
                logger.error(f"[Frontlama] Loop error: {e}", exc_info=True)
                await asyncio.sleep(self.frontlama_interval)
    
    async def _run_frontlama_cycle(self):
        """
        Single frontlama cycle:
        1. Get all active orders
        2. Get current exposure
        3. For each order, get truth tick and L1 data
        4. Evaluate frontlama decision
        5. If approved, modify order
        """
        logger.debug("[Frontlama] Running cycle...")
        
        # 1. Get active orders
        open_orders = await self._get_open_orders()
        if not open_orders:
            logger.debug("[Frontlama] No active orders to evaluate")
            return
        
        # 2. Get current exposure
        exposure_pct = await self._get_current_exposure_pct()
        
        # 3. Process each order
        fronted_count = 0
        evaluated_count = 0
        
        for order in open_orders:
            try:
                symbol = order.get('symbol', '')
                if not symbol:
                    continue
                
                evaluated_count += 1
                
                # Get L1 data
                l1_data = await self._get_l1_data(symbol)
                
                # Get latest truth tick
                truth_last, truth_venue, truth_size = await self._get_latest_truth_tick(symbol)
                
                # Evaluate frontlama
                decision = self.frontlama_engine.evaluate_order_for_frontlama(
                    order=order,
                    l1_data=l1_data,
                    truth_last=truth_last,
                    truth_venue=truth_venue,
                    truth_size=truth_size,
                    exposure_pct=exposure_pct
                )
                
                # Log decision
                self._log_frontlama_decision(symbol, order, decision)
                
                # If approved, modify order
                if decision.allowed and decision.front_price:
                    success = await self._modify_order_price(order, decision.front_price)
                    if success:
                        fronted_count += 1
                        logger.info(
                            f"[Frontlama] ✓ {symbol} ORDER MODIFIED: "
                            f"${order.get('price', 0):.2f} → ${decision.front_price:.2f} "
                            f"(sacrifice={decision.sacrificed_cents:.2f}¢)"
                        )
            
            except Exception as e:
                logger.error(f"[Frontlama] Error processing order {order.get('symbol', 'UNKNOWN')}: {e}")
        
        if fronted_count > 0:
            logger.info(f"[Frontlama] 📊 Cycle complete: {fronted_count}/{evaluated_count} orders fronted")
        else:
            logger.debug(f"[Frontlama] Cycle complete: 0/{evaluated_count} orders fronted")
    
    async def _get_current_exposure_pct(self) -> float:
        """
        Get current portfolio exposure percentage.
        
        exposure_pct = (pot_total / pot_max) × 100
        
        Sources (priority order):
        1. Redis cache: psfalgo:exposure:{account} (5-min TTL, written by exposure_calculator)
        2. Live calculation: calculate_exposure_for_account() 
        3. Default: 65% (neutral zone)
        """
        try:
            import json
            
            # ── SOURCE 1: Redis cache (fast, no async needed) ──
            if self.redis_client:
                redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
                key = f"psfalgo:exposure:{self.account_mode}"
                data = redis_sync.get(key)
                
                if data:
                    raw = data.decode() if isinstance(data, bytes) else data
                    exposure = json.loads(raw)
                    pot_total = float(exposure.get('pot_total', 0))
                    pot_max = float(exposure.get('pot_max', 1))
                    
                    if pot_max > 0:
                        pct = (pot_total / pot_max) * 100
                        logger.debug(f"[Frontlama] Exposure from Redis: {pct:.1f}% ({self.account_mode})")
                        return pct
            
            # ── SOURCE 2: Live calculation (async, slower but always accurate) ──
            try:
                from app.psfalgo.exposure_calculator import calculate_exposure_for_account
                exposure = await calculate_exposure_for_account(self.account_mode)
                if exposure and exposure.pot_max > 0:
                    pct = (exposure.pot_total / exposure.pot_max) * 100
                    logger.debug(f"[Frontlama] Exposure from LIVE calc: {pct:.1f}% ({self.account_mode})")
                    return pct
            except Exception as e:
                logger.debug(f"[Frontlama] Live exposure calc failed: {e}")
            
            # ── SOURCE 3: Default ──
            logger.debug(f"[Frontlama] Exposure defaulting to 65% ({self.account_mode})")
            return 65.0
            
        except Exception as e:
            logger.error(f"[Frontlama] Exposure fetch error: {e}")
            return 65.0
    
    async def _get_latest_truth_tick(self, symbol: str) -> tuple:
        """
        Get the latest valid truth tick for a symbol.
        
        Reads from tt:ticks:{symbol} (written by TruthTicksEngine, 12-day TTL).
        This is the canonical source - always available even when workers restart.
        
        For illiquid preferred stocks, truth ticks may be hours old in market time.
        Staleness is checked against the tick's timestamp.
        
        Returns:
            (truth_last, truth_venue, truth_size) or (None, None, None) if no valid tick
        """
        try:
            if not self.redis_client:
                return None, None, None
            
            import json
            import time
            
            # CRITICAL: Use .sync.get() for consistency (same as all other Redis reads)
            redis_sync = getattr(self.redis_client, 'sync', self.redis_client)
            
            # PRIMARY SOURCE: tt:ticks:{symbol} (TruthTicksEngine, 12-day TTL)
            key = f"tt:ticks:{symbol}"
            data = redis_sync.get(key)
            
            if data:
                raw = data.decode() if isinstance(data, bytes) else data
                ticks = json.loads(raw)
                
                if not ticks or not isinstance(ticks, list):
                    return None, None, None
                
                now = time.time()
                # Iterate from NEWEST to oldest (list is chronological, newest at end)
                for tick in reversed(ticks):
                    tick_ts = tick.get('ts', 0)
                    if tick_ts > 0:
                        age_seconds = now - tick_ts
                        # Allow up to 24 hours (illiquid stocks + overnight)
                        if age_seconds > 86400:
                            continue  # STALE — skip, try older ticks
                    
                    price = float(tick.get('price', 0))
                    size = float(tick.get('size', 0))
                    venue = str(tick.get('exch', tick.get('venue', '')))
                    
                    if price > 0 and size > 0:
                        return (price, venue, size)
                
                # All ticks stale
                logger.debug(
                    f"[Frontlama] All truth ticks for {symbol} are stale (>24h)"
                )
                return None, None, None
            
            # FALLBACK: truthtick:latest:{symbol} (legacy, short TTL)
            legacy_key = f"truthtick:latest:{symbol}"
            legacy_data = redis_sync.get(legacy_key)
            if legacy_data:
                raw = legacy_data.decode() if isinstance(legacy_data, bytes) else legacy_data
                tick = json.loads(raw)
                price = float(tick.get('price', 0))
                size = float(tick.get('size', 0))
                venue = str(tick.get('venue', tick.get('exch', '')))
                tick_ts = float(tick.get('ts', 0))
                # ⚠️ STALENESS CHECK: same 24h limit
                if price > 0 and size > 0:
                    if tick_ts > 0 and (time.time() - tick_ts) > 86400:
                        return None, None, None  # STALE
                    return (price, venue, size)
            
            return None, None, None
            
        except Exception as e:
            logger.error(f"[Frontlama] Truth tick fetch error for {symbol}: {e}")
            return None, None, None
    
    async def _modify_order_price(self, order: Dict, new_price: float) -> bool:
        """
        ATOMIC order modify — no cancel gap, same order ID preserved.
        
        HAMPRO: Uses tradeCommandModify (single API call, atomic)
        IBKR:   Uses placeOrder with existing orderId (native IBKR modify)
        
        Falls back to cancel+replace ONLY if atomic modify fails.
        
        SAFETY: Pre-checks provider readiness before attempting.
        """
        try:
            import asyncio
            
            order_id = order.get('order_id', order.get('id', ''))
            symbol = order.get('symbol', '')
            account_id = self.account_mode or ''
            
            if not order_id:
                logger.warning(f"[Frontlama] Cannot modify order without order_id: {symbol}")
                return False
            
            # ── PRE-CHECK: Execution provider must be connected ──
            if not self._is_execution_ready():
                logger.debug(f"[Frontlama] Skipping modify for {symbol}: execution not ready")
                return False
            
            # ═══════════════════════════════════════════════════════════════
            # PATH 1: ATOMIC MODIFY via Execution Provider (preferred)
            # ═══════════════════════════════════════════════════════════════
            try:
                from app.execution.execution_router import get_execution_router
                from app.trading.trading_account_context import TradingAccountMode
                
                router = get_execution_router()
                
                # Map account_id to TradingAccountMode
                if account_id in ("HAMPRO", "HAMMER_PRO"):
                    mode_enum = TradingAccountMode.HAMPRO
                elif account_id == "IBKR_PED":
                    mode_enum = TradingAccountMode.IBKR_PED
                elif account_id == "IBKR_GUN":
                    mode_enum = TradingAccountMode.IBKR_GUN
                else:
                    mode_enum = None
                
                if mode_enum and router:
                    provider = router.providers.get(mode_enum)
                    if provider:
                        loop = asyncio.get_event_loop()
                        success = await loop.run_in_executor(
                            None,
                            lambda: provider.replace_order(
                                account_id=account_id,
                                order_id=str(order_id),
                                new_price=float(new_price)
                            )
                        )
                        
                        if success:
                            logger.info(
                                f"[Frontlama] ✅ ATOMIC modify {symbol} order {order_id}: "
                                f"${order.get('price', 0):.2f} → ${new_price:.2f} "
                                f"(same ID, no cancel gap) [{account_id}]"
                            )
                            return True
                        else:
                            logger.warning(
                                f"[Frontlama] Atomic modify failed for {symbol} order {order_id}, "
                                f"falling back to cancel+replace [{account_id}]"
                            )
            except Exception as e:
                logger.warning(f"[Frontlama] Atomic modify path error: {e}, falling back to cancel+replace")
            
            # ═══════════════════════════════════════════════════════════════
            # PATH 2: FALLBACK — Cancel + Replace (legacy, non-atomic)
            # Only used if atomic modify fails
            # PRE-CHECK: Backend must be reachable to avoid 5s timeout blocks
            # ═══════════════════════════════════════════════════════════════
            if not self._is_backend_reachable():
                logger.debug(f"[Frontlama] Skipping fallback modify for {symbol}: backend not reachable")
                return False
            
            import requests
            
            # Cancel existing order
            cancel_endpoint = "http://localhost:8000/api/orders/cancel"
            cancel_response = requests.post(
                cancel_endpoint,
                json={'order_id': order_id, 'account_id': account_id},
                timeout=3
            )
            
            if cancel_response.status_code != 200:
                logger.error(f"[Frontlama] Fallback cancel failed for order {order_id}")
                return False
            
            # Place new order at front price (with FR_ tag prefix)
            place_endpoint = "http://localhost:8000/api/orders/place"
            original_tag = order.get('tag', order.get('strategy_tag', 'FRONTED'))
            fr_tag = original_tag
            if not fr_tag.upper().startswith('FR_'):
                fr_tag = f"FR_{fr_tag}"
            
            new_order = {
                'symbol': symbol,
                'side': order.get('action', order.get('side', '')),
                'qty': order.get('qty', order.get('quantity', 0)),
                'price': new_price,
                'order_type': 'LIMIT',
                'hidden': True,
                'strategy_tag': fr_tag,
                'account_id': account_id
            }
            
            place_response = requests.post(place_endpoint, json=new_order, timeout=3)
            
            if place_response.status_code == 200:
                result = place_response.json()
                if result.get('success', False):
                    logger.info(
                        f"[Frontlama] ⚠️ {symbol} order modified via FALLBACK cancel+replace "
                        f"(old ID lost, new order placed) [{account_id}]"
                    )
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"[Frontlama] Order modify error: {e}", exc_info=True)
            return False
    
    def _log_frontlama_decision(self, symbol: str, order: Dict, decision: FrontlamaDecision):
        """Log frontlama decision details"""
        if decision.allowed:
            logger.info(
                f"[Frontlama] ✓ {symbol} APPROVED: "
                f"base=${decision.base_price:.2f} → front=${decision.front_price:.2f} "
                f"(sacrifice={decision.sacrificed_cents:.2f}¢ = {decision.sacrifice_ratio:.1%}) "
                f"[{decision.tag.value}] [exp={decision.exposure_pct:.1f}%]"
            )
        else:
            logger.debug(
                f"[Frontlama] ✗ {symbol} DENIED: {decision.reason} "
                f"[{decision.tag.value}] [exp={decision.exposure_pct:.1f}%]"
            )