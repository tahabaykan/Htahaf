"""
Hammer Fills Listener
Listens to Hammer Pro 'transactionsUpdate' messages and logs fills to DailyFillsStore.
"""

from typing import Dict, Any, Optional, Set
from datetime import datetime
from app.core.logger import logger
from app.trading.daily_fills_store import get_daily_fills_store

class HammerFillsListener:
    """ Observer for Hammer Client messages to capture fills. """

    def __init__(self):
        self._order_tags: Dict[str, str] = {} # OrderID -> Strategy Tag
        self._processed_fill_ids: Set[str] = set() # Avoid duplicates
        # If FillID not available, dedupe by OrderID-Qty-Price combo?
        self._processed_events: Set[str] = set() 

    def register_order(self, order_id: str, tag: str):
        """ Register a strategy tag for an OrderID """
        if order_id and tag:
            self._order_tags[order_id] = tag
            # logger.debug(f"[HammerFills] Registered Order {order_id} with tag {tag}")

    def on_message(self, message: Dict[str, Any]):
        """ Handle incoming Hammer message """
        try:
            cmd = message.get("cmd")
            
            if cmd == "transactionsUpdate":
                self._handle_transactions_update(message)
                
        except Exception as e:
            logger.error(f"[HammerFills] Error processing message: {e}", exc_info=True)

    def _handle_transactions_update(self, message: Dict[str, Any]):
        result = message.get("result", {})
        transactions = result.get("transactions", [])
        
        for tx in transactions:
            # Check for filled status or usage of Fills array
            # Logic: If 'Fills' array exists, iterate it.
            # Else if StatusID == 'Filled' and 'FilledQTY' > 0, treat as fill (but be careful of partials)
            
            order_id = str(tx.get("OrderID", ""))
            symbol = tx.get("Symbol", "")
            action = tx.get("Action", "BUY").upper()
            
            # Use registered tag or resolve from Redis if not in memory
            strategy_tag = self._order_tags.get(order_id)
            if not strategy_tag and order_id:
                strategy_tag = self._resolve_tag_from_redis(order_id, symbol, action, tx)
            
            fills = tx.get("Fills", [])
            
            if fills:
                # Iterate explicit fills
                for fill in fills:
                    self._log_single_fill(
                        fill_id=str(fill.get("FillID")),
                        symbol=symbol,
                        action=action,
                        qty=float(fill.get("QTY", 0)),
                        price=float(fill.get("Price", 0)),
                        tag=strategy_tag
                    )
            else:
                # No fills array, check generic fields
                # Only if StatusID is Filled or generic 'FilledQTY' increases?
                # The 'New' flag helps. Or 'changesOnly' mode.
                # If StatusID is Filled or Partial, we might have data.
                # But without FillID, deduplication is hard.
                # We will construct a synthetic FillID: OrderID_FilledQTY
                
                status = tx.get("StatusID", "")
                filled_qty = float(tx.get("FilledQTY", 0))
                filled_price = float(tx.get("FilledPrice", 0)) # Average price?
                
                # Only log if we have actual filled qty
                if filled_qty > 0 and status in ["Filled", "PartiallyFilled"]:
                    # Synthetic ID
                    # Note: If order fills 100, then 200... we get 100 then 200 total?
                    # API says "FilledQTY". Usually cumulative.
                    # Creating delta is complex without state.
                    # BUT we switched to 'changes=True'. 
                    # Does 'changes=True' send *deltas* or just *changed records*?
                    # "The transactionsUpdate... will always include only new or changed transactions."
                    # It returns the Transaction Object. The Transaction Object usually has Cumulative FilledQTY.
                    # If I see FilledQTY=100, then FilledQTY=200... 
                    # I need to log the *diff*.
                    # For now, let's assume 'Fills' array is present for granular updates as per example.
                    # If 'Fills' is missing, fallback is risky.
                    
                    # Log the cumulative as a single fill if it looks like a one-shot? 
                    # Or warn?
                    pass 

    def _resolve_tag_from_redis(self, order_id: str, symbol: str, action: str, tx: Dict[str, Any]) -> str:
        """Resolve strategy tag from Redis for fire-and-forget orders.
        
        Resolution priority:
        1. Direct lookup: hammer:order_tag:{order_id} (set by normal-mode place_order)
        2. Pending tag:   hammer:pending_tag:{symbol}:{action}:{qty} (set by fire-and-forget place_order)
        3. API field:     OrderRef / Tag from the transaction itself
        """
        try:
            from app.core.redis_client import get_redis_client
            redis = get_redis_client()
            if not redis:
                logger.warning(f"[HammerFills] Redis unavailable, cannot resolve tag for order {order_id}")
                return "UNKNOWN"
            
            # 1. Direct lookup (order was placed with normal confirmation, or previously resolved)
            direct_key = f"hammer:order_tag:{order_id}"
            tag = redis.get(direct_key)
            if tag:
                tag_str = tag if isinstance(tag, str) else tag.decode('utf-8')
                self._order_tags[order_id] = tag_str  # Cache in memory
                return tag_str
            
            # 2. Pending tag (fire-and-forget: matched by symbol+action+qty)
            #    CRITICAL: HammerExecutionService writes with Capitalized action ("Buy", "Sell")
            #    but Hammer API sends back action in various cases ("Buy", "BUY", etc.)
            #    We try multiple case variants AND multiple qty field names.
            #    Hammer API may return qty as: Quantity, OrderQTY, QTY, FilledQTY
            qty = 0
            for qty_field in ["Quantity", "OrderQTY", "QTY", "OriginalQTY"]:
                val = tx.get(qty_field)
                if val and int(val) > 0:
                    qty = int(val)
                    break
            
            if qty > 0:
                # Try all possible action case variants
                action_variants = list(dict.fromkeys([
                    action,                     # Original (e.g. "BUY")
                    action.capitalize(),         # Capitalized (e.g. "Buy") — HammerExecService uses this
                    action.upper(),              # Upper (e.g. "BUY")
                    action.lower(),              # Lower (e.g. "buy")
                ]))
                
                for action_variant in action_variants:
                    pending_key = f"hammer:pending_tag:{symbol}:{action_variant}:{qty}"
                    pending_tag = redis.get(pending_key)
                    if pending_tag:
                        tag_str = pending_tag if isinstance(pending_tag, str) else pending_tag.decode('utf-8')
                        # Strip venue suffix for clean base tag
                        base_tag = tag_str.split('__V')[0] if '__V' in tag_str else tag_str
                        redis.set(f"hammer:order_tag:{order_id}", base_tag, ex=86400)
                        self._order_tags[order_id] = base_tag
                        logger.info(f"[HammerFills] ✅ Resolved pending tag: {order_id} -> {base_tag} (variant={action_variant}, qty={qty})")
                        return base_tag
                
                # 2b. FALLBACK: Try symbol+action:ANY key (for partial fills with mismatched qty)
                for action_variant in action_variants:
                    any_key = f"hammer:pending_tag:{symbol}:{action_variant}:ANY"
                    any_tag = redis.get(any_key)
                    if any_tag:
                        tag_str = any_tag if isinstance(any_tag, str) else any_tag.decode('utf-8')
                        base_tag = tag_str.split('__V')[0] if '__V' in tag_str else tag_str
                        redis.set(f"hammer:order_tag:{order_id}", base_tag, ex=86400)
                        self._order_tags[order_id] = base_tag
                        logger.info(f"[HammerFills] ✅ Resolved pending tag (ANY fallback): {order_id} -> {base_tag} (variant={action_variant})")
                        return base_tag
            
            # 3. Fallback: Check if Hammer API returned an orderRef/tag in the transaction itself
            api_tag = tx.get("OrderRef") or tx.get("orderRef") or tx.get("Tag") or tx.get("tag") or tx.get("orderTag")
            if api_tag and str(api_tag).strip():
                tag_str = str(api_tag).strip()
                redis.set(f"hammer:order_tag:{order_id}", tag_str, ex=86400)
                self._order_tags[order_id] = tag_str
                logger.info(f"[HammerFills] ✅ Resolved tag from API field: {order_id} -> {tag_str}")
                return tag_str
                    
        except Exception as e:
            logger.warning(f"[HammerFills] ⚠️ Redis tag resolve error for {order_id}: {e}")
        
        logger.debug(f"[HammerFills] Redis tag miss for order {order_id} ({symbol} {action}), trying inference...")
        
        # 4. LAST RESORT: Infer tag from position context
        #    When Redis keys have expired (restart/recovery), we can still determine
        #    the likely tag based on current position direction + action.
        inferred = self._infer_tag_from_position(symbol, action)
        if inferred:
            # Cache this for future lookups to avoid repeated inference
            try:
                from app.core.redis_client import get_redis_client
                r = get_redis_client()
                if r:
                    r.set(f"hammer:order_tag:{order_id}", inferred, ex=86400)
            except Exception:
                pass
            self._order_tags[order_id] = inferred
            logger.debug(f"[HammerFills] 🔮 Inferred tag: {order_id} ({symbol} {action}) -> {inferred}")
            return inferred
        
        logger.warning(f"[HammerFills] ❌ Could not resolve tag for order {order_id} ({symbol} {action}) — no inference available")
        return "UNKNOWN"

    def _infer_tag_from_position(self, symbol: str, action: str) -> Optional[str]:
        """
        Infer a likely strategy tag from current position context.
        Used as last resort when Redis tag lookup fails (e.g., after restart).
        
        Tag format: {SOURCE}_{DIRECTION}_{ACTION}
        
        SOURCE  → from Internal Ledger's LT/MM split (NOT from Redis positions which may be stale)
        DIRECTION → from position qty sign: qty > 0 = LONG, qty < 0 = SHORT
        ACTION  → from fill action + position direction:
                   LONG + SELL = DEC (trimming long)
                   LONG + BUY  = INC (adding to long)
                   SHORT + BUY  = DEC (covering short)
                   SHORT + SELL = INC (adding to short)
        
        Resolution layers:
        1. Internal Ledger → LT/MM split (ground truth)
        2. Today's fill log → most recent tag used for this symbol
        3. Default → LT_INC (new position assumption)
        
        NOTE: Cannot determine REV/FR prefix — that info is only available at order send time.
        """
        action_upper = action.upper()
        
        # ═══════════════════════════════════════════════════════════════
        # Layer 1: Check Internal Ledger for LT/MM book (GROUND TRUTH)
        # ═══════════════════════════════════════════════════════════════
        try:
            from app.psfalgo.internal_ledger_store import get_internal_ledger_store
            import json
            ledger = get_internal_ledger_store()
            
            # We need current qty to determine mm_qty = broker_qty - lt_qty
            broker_qty = None
            
            # Get broker qty from Redis positions
            from app.core.redis_client import get_redis_client
            redis = get_redis_client()
            if redis:
                for account_key in ["HAMPRO", "HAMMER_PRO", "IBKR_PED"]:
                    positions_key = f"psfalgo:positions:{account_key}"
                    raw = redis.get(positions_key)
                    if raw:
                        try:
                            data_str = raw if isinstance(raw, str) else raw.decode('utf-8')
                            positions = json.loads(data_str)
                            if isinstance(positions, dict) and symbol in positions:
                                broker_qty = float(positions[symbol].get('qty', 0))
                                
                                # Determine source from Internal Ledger
                                source = "LT"  # default
                                if ledger and ledger.has_symbol(account_key, symbol):
                                    lt_qty = ledger.get_lt_quantity(account_key, symbol)
                                    mm_qty = broker_qty - lt_qty
                                    if abs(mm_qty) > abs(lt_qty) and abs(mm_qty) > 0.01:
                                        source = "MM"
                                
                                # Determine direction and inc/dec
                                if broker_qty > 0:  # LONG position
                                    direction = "LONG"
                                    inc_dec = "DEC" if action_upper == "SELL" else "INC"
                                elif broker_qty < 0:  # SHORT position
                                    direction = "SHORT"
                                    inc_dec = "DEC" if action_upper in ("BUY", "COVER") else "INC"
                                else:
                                    # qty = 0: new position opening
                                    direction = "LONG" if action_upper == "BUY" else "SHORT"
                                    inc_dec = "INC"
                                
                                tag = f"{source}_{direction}_{inc_dec}"
                                logger.debug(f"[HammerFills] 🔮 Inferred tag from Ledger: {symbol} {action} → {tag} "
                                           f"(lt={lt_qty if ledger else '?'}, mm={mm_qty if ledger else '?'})")
                                return tag
                        except (json.JSONDecodeError, AttributeError):
                            continue
        except Exception as e:
            logger.debug(f"[HammerFills] Ledger-based inference failed: {e}")
        
        # ═══════════════════════════════════════════════════════════════
        # Layer 2: Check today's fill CSV log for recent tags of same symbol
        # If we've already filled orders for this symbol today, use the
        # most recent tag's source (LT/MM) for consistency
        # ═══════════════════════════════════════════════════════════════
        try:
            from app.trading.daily_fills_store import get_daily_fills_store
            store = get_daily_fills_store()
            if store:
                recent_fills = store.get_fills_for_symbol(symbol) if hasattr(store, 'get_fills_for_symbol') else []
                for fill in reversed(recent_fills):
                    fill_tag = fill.get('tag', fill.get('strategy_tag', ''))
                    if fill_tag and fill_tag != 'UNKNOWN':
                        # Extract source (LT or MM) from existing tag
                        tag_upper = fill_tag.upper()
                        if 'MM' in tag_upper:
                            source = 'MM'
                        elif 'LT' in tag_upper or 'PAT' in tag_upper:
                            source = 'LT'
                        else:
                            continue
                        
                        direction = "LONG" if action_upper == "BUY" else "SHORT"
                        inc_dec = "INC"
                        # If there's an existing position, determine INC/DEC
                        if broker_qty is not None:
                            if broker_qty > 0:
                                direction = "LONG"
                                inc_dec = "DEC" if action_upper == "SELL" else "INC"
                            elif broker_qty < 0:
                                direction = "SHORT"
                                inc_dec = "DEC" if action_upper in ("BUY", "COVER") else "INC"
                        
                        tag = f"{source}_{direction}_{inc_dec}"  # 3-part (no engine info) — OK for substring matching
                        logger.debug(f"[HammerFills] 🔮 Inferred tag from fill history: {symbol} {action} → {tag}")
                        return tag
        except Exception:
            pass
        
        # ═══════════════════════════════════════════════════════════════
        # Layer 3: Default fallback — LT (new position assumed)
        # ═══════════════════════════════════════════════════════════════
        direction = "LONG" if action_upper == "BUY" else "SHORT"
        tag = f"MM_MM_{direction}_INC"  # v4 default: unknown fills → MM
        logger.debug(f"[HammerFills] 🔮 Default inferred tag: {symbol} {action} → {tag}")
        return tag

    def _log_single_fill(self, fill_id: str, symbol: str, action: str, qty: float, price: float, tag: str):
        if fill_id in self._processed_fill_ids:
            return
            
        self._processed_fill_ids.add(fill_id)
        
        # Log to DailyFillsStore (benchmark auto-fetched inside log_fill if not provided)
        try:
            store = get_daily_fills_store()
            
            # DailyFillsStore.log_fill will auto-fetch bench_chg from DataFabric
            # CRITICAL: Fetch bid/ask from shared market_data_cache NOW
            # Hammer symbols are dash format (PSA-N) but cache uses display (PSA PRN)
            _fill_bid, _fill_ask = None, None
            try:
                from app.api.market_data_routes import get_market_data
                from app.live.symbol_mapper import SymbolMapper
                for _sym_variant in [symbol, SymbolMapper.to_display_symbol(symbol), SymbolMapper.to_hammer_symbol(symbol)]:
                    _md = get_market_data(_sym_variant)
                    if _md and _md.get('bid') and _md.get('ask') and float(_md['bid']) > 0 and float(_md['ask']) > 0:
                        _fill_bid = float(_md['bid'])
                        _fill_ask = float(_md['ask'])
                        break
            except Exception:
                pass
            store.log_fill(
                account_type="HAMMER_PRO", 
                symbol=symbol, 
                action=action, 
                qty=qty, 
                price=price, 
                strategy_tag=tag,
                fill_id=fill_id,
                bid=_fill_bid,
                ask=_fill_ask
            )
            logger.info(f"🔨 [HAMMER FILL] Logged {symbol} {action} {qty} @ {price} ({tag})")

            # ── Update Dual Tag System v4 (POS TAG store) ──
            try:
                from app.psfalgo.fill_tag_handler import handle_fill_for_tagging
                from app.live.symbol_mapper import SymbolMapper
                # CRITICAL: Convert Hammer symbol (WBS-F) to display format (WBS PRF)
                # Redis positions are keyed by DISPLAY format (written by position_redis_worker
                # and position_snapshot_api). Without this conversion, fill_tag_handler creates
                # a DUPLICATE entry (WBS-F) instead of updating the existing one (WBS PRF),
                # causing MinMax to read stale qty values.
                display_sym_for_tag = SymbolMapper.to_display_symbol(symbol)
                handle_fill_for_tagging(
                    symbol=display_sym_for_tag,
                    fill_qty=qty,
                    action=action,
                    source=tag,
                    tag=tag,
                    account_id='HAMPRO'
                )
            except Exception as tag_err:
                logger.debug(f"[HammerFills] Dual Tag update error: {tag_err}")

            # ── Update OrderLifecycleTracker (fill price available here) ──
            try:
                from app.monitoring.order_lifecycle_tracker import get_order_lifecycle_tracker
                from app.live.symbol_mapper import SymbolMapper
                tracker = get_order_lifecycle_tracker()
                # CRITICAL: Convert Hammer symbol (WBS-F) to display format (WBS PRF)
                # so tracker can: 1) match against sent orders, 2) look up truth ticks,
                # 3) look up L1 bid/ask from DataFabric — all stored in display format.
                display_sym = SymbolMapper.to_display_symbol(symbol)
                tracker.on_fill(
                    symbol=display_sym,
                    action=action,
                    fill_price=price,
                    tag=tag,
                    account_id='HAMPRO',
                    fill_qty=int(qty),
                )
            except Exception as tracker_err:
                logger.debug(f"[HammerFills] OrderLifecycleTracker error: {tracker_err}")

            # Notify Redis Stream (Phase 10.3: RevOrder Bildiri)
            # Include bench_chg for downstream consumers
            try:
                from app.core.event_bus import EventBus
                from app.live.symbol_mapper import SymbolMapper
                
                # Fetch bench_chg for Redis stream too
                bench_chg, bench_source = store._fetch_benchmark_for_symbol(symbol)
                
                # CRITICAL: Write BOTH Hammer format AND display format to ledger
                # so _lookup_fill_price can match regardless of which format is used.
                display_sym = SymbolMapper.to_display_symbol(symbol)
                
                ledger_data = {
                    "event": "FILL",
                    "order_id": str(tag), # Strategy tag as order_ref
                    "fill_id": str(fill_id),
                    "symbol": symbol,             # Hammer format (e.g. BML-H)
                    "display_symbol": display_sym, # Display format (e.g. BML PRH)
                    "tag": str(tag),               # Strategy tag for source detection
                    "qty": str(qty),
                    "price": str(price),
                    "action": action,
                    "account_id": "HAMPRO", # Hammer Pro
                    "timestamp": datetime.now().isoformat(),
                }
                if bench_chg is not None:
                    ledger_data["bench_chg"] = str(round(bench_chg, 4))
                    ledger_data["bench_source"] = bench_source or ""
                
                EventBus.xadd(stream="psfalgo:execution:ledger", data=ledger_data)
            except Exception as rb:
                 logger.error(f"[HammerFills] Redis Bildiri Error: {rb}")
        except Exception as e:
            logger.error(f"[HammerFills] Failed to log fill: {e}")

# Global instance
_hammer_fills_listener = None

def get_hammer_fills_listener():
    global _hammer_fills_listener
    if not _hammer_fills_listener:
        _hammer_fills_listener = HammerFillsListener()
    return _hammer_fills_listener
