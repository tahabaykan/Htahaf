"""
Fill → PositionTagManager + PositionTagStore Bridge

Updates both PositionTagManager (int/ov tracking) and PositionTagStore (POS TAG: MM/LT)
when orders are filled. This ensures position tags are correctly tracked.

Dual Tag System v4:
- POS TAG (MM/LT) stored in PositionTagStore (Redis-backed, per-account)
- ENGINE TAG extracted from order tag (MM/PA/AN/KB/TRIM)
"""
from typing import Optional
from app.core.logger import logger


def _extract_engine_tag(tag: str) -> str:
    """
    Extract ENGINE TAG from order tag.
    
    Dual-tag v4 format: {POS}_{ENGINE}_{DIR}_{ACTION}
    e.g. MM_MM_LONG_INC → ENGINE=MM
         LT_PA_LONG_INC → ENGINE=PA
         REV_TP_LT_PA_SELL → ENGINE=PA
         FR_MM_MM_LONG_INC → ENGINE=MM
    
    Legacy format fallback:
         MM_LONG_INC → ENGINE=MM
         KARBOTU_LONG_DEC → ENGINE=KB
    """
    if not tag:
        return "MM"
    
    clean = tag.upper().replace('FR_', '').replace('REV_TP_', '').replace('REV_RL_', '').replace('OZEL_', '')
    parts = clean.split('_')
    
    # v4 format: POS_ENGINE_DIR_ACTION (≥4 parts)
    if len(parts) >= 4 and parts[0] in ('MM', 'LT'):
        engine = parts[1]
        if engine in ('MM', 'PA', 'AN', 'KB', 'TRIM'):
            return engine
    
    # v4 REV format already stripped: POS_ENGINE_ACTION → ENGINE is parts[1]
    if len(parts) >= 3 and parts[0] in ('MM', 'LT'):
        engine = parts[1]
        if engine in ('MM', 'PA', 'AN', 'KB', 'TRIM'):
            return engine
    
    # Legacy fallback
    if 'KARBOTU' in clean or 'HEAVY' in clean:
        return 'KB'
    if 'TRIM' in clean:
        return 'TRIM'
    if 'PATADD' in clean or 'PAT' in clean:
        return 'PA'
    if 'ADDNEWPOS' in clean:
        return 'AN'
    if clean.startswith('MM'):
        return 'MM'
    
    return 'MM'


def handle_fill_for_tagging(
    symbol: str, 
    fill_qty: float, 
    action: str, 
    source: str,
    tag: str = "",
    is_new_position: bool = False,
    account_id: str = None
):
    """
    Update PositionTagManager + PositionTagStore when a fill is received.
    
    Args:
        symbol: Stock symbol
        fill_qty: Filled quantity (positive number)
        action: 'BUY' or 'SELL'
        source: Order source/engine name (e.g., 'ADDNEWPOS', 'GREATEST_MM')
        tag: Full order tag string (e.g., 'LT_PA_LONG_INC', 'MM_MM_SHORT_INC')
        is_new_position: True if this is a new position (no prior position)
        account_id: Account ID (HAMPRO or IBKR_PED) for per-account POS TAG
    """
    # ── 1. Update legacy PositionTagManager (int/ov tracking) ──
    try:
        from app.psfalgo.position_tags import get_position_tag_manager
        tag_manager = get_position_tag_manager()
        
        source_upper = source.upper() if source else ''
        is_mm = 'MM' in source_upper or 'GREATEST' in source_upper
        
        directed_qty = abs(fill_qty) if action == 'BUY' else -abs(fill_qty)
        
        tag_manager.update_on_fill(
            symbol=symbol, 
            fill_qty=directed_qty, 
            is_new_position=is_new_position, 
            is_mm=is_mm
        )
    except Exception as e:
        logger.debug(f"[FILL_TAG] PositionTagManager update error: {e}")
    
    # ── 2. Update PositionTagStore (POS TAG: MM/LT, Dual Tag v4, per-account) ──
    try:
        from app.psfalgo.position_tag_store import get_position_tag_store
        store = get_position_tag_store()
        if store:
            engine_tag = _extract_engine_tag(tag or source)
            store.update_on_fill(symbol, engine_tag, account_id)
            
            new_pos_tag = store.get_tag(symbol, account_id)
            logger.info(
                f"[FILL_TAG] {symbol}: {action} {fill_qty} | "
                f"engine={engine_tag} | pos_tag={new_pos_tag} | tag={tag} | acct={account_id}"
            )
    except Exception as e:
        logger.debug(f"[FILL_TAG] PositionTagStore update error: {e}")
    
    # ── 3. CRITICAL: Update Redis positions ATOMICALLY (so MinMax sees fresh qty) ──
    # Uses WATCH/MULTI/EXEC to prevent race conditions when multiple fills
    # arrive simultaneously (e.g. ONBPO overselling incident 2026-03-16).
    # Without atomicity: GET(100) → -100 → SET(0) x2 = 0, but should be -100!
    try:
        from app.core.redis_client import get_redis_client
        import json
        import time as _time
        redis = get_redis_client()
        if redis and account_id:
            pos_key = f"psfalgo:positions:{account_id}"
            redis_sync = getattr(redis, 'sync', redis)
            
            directed_qty = abs(fill_qty) if action.upper() in ('BUY', 'ADD', 'COVER') else -abs(fill_qty)
            
            # Atomic update with retry (optimistic locking)
            MAX_RETRIES = 3
            updated = False
            for attempt in range(MAX_RETRIES):
                try:
                    # WATCH the key — if another fill modifies it before EXEC, retry
                    redis_sync.watch(pos_key)
                    
                    raw = redis_sync.get(pos_key)
                    if not raw:
                        redis_sync.unwatch()
                        break
                    
                    data_str = raw if isinstance(raw, str) else raw.decode('utf-8')
                    positions = json.loads(data_str)
                    if not isinstance(positions, dict):
                        redis_sync.unwatch()
                        break
                    
                    if symbol in positions:
                        old_qty = float(positions[symbol].get('qty', 0))
                        new_qty = old_qty + directed_qty
                        positions[symbol]['qty'] = new_qty
                        positions[symbol]['potential_qty'] = new_qty
                    else:
                        old_qty = 0.0
                        new_qty = directed_qty
                        positions[symbol] = {
                            'symbol': symbol,
                            'qty': new_qty,
                            'potential_qty': new_qty,
                            'befday_qty': 0.0,
                        }
                    
                    positions['_meta'] = {'updated_at': _time.time()}
                    
                    # MULTI/EXEC — atomic write (fails if key was modified since WATCH)
                    pipe = redis_sync.pipeline(True)  # True = MULTI mode
                    pipe.set(pos_key, json.dumps(positions), ex=3600)
                    pipe.execute()
                    
                    updated = True
                    logger.info(
                        f"[FILL_TAG] ✅ Redis positions updated (atomic): {symbol} "
                        f"qty {old_qty:.0f} → {new_qty:.0f} ({account_id})"
                    )
                    
                    # ── Check if position is now closed (qty=0) → clean up POS TAG ──
                    if abs(new_qty) < 0.01:
                        handle_position_closed(symbol, account_id)
                    
                    break  # Success, exit retry loop
                    
                except Exception as watch_err:
                    # WatchError = another fill modified the key → retry
                    err_name = type(watch_err).__name__
                    if 'WatchError' in err_name or 'watch' in str(watch_err).lower():
                        logger.warning(
                            f"[FILL_TAG] ⚡ Concurrent fill detected for {symbol} "
                            f"(attempt {attempt+1}/{MAX_RETRIES}) — retrying atomic update"
                        )
                        continue
                    else:
                        raise  # Re-raise non-watch errors
            
            if not updated and raw:
                logger.warning(
                    f"[FILL_TAG] ⚠️ Failed to update Redis positions for {symbol} "
                    f"after {MAX_RETRIES} retries ({account_id})"
                )
    except Exception as e:
        logger.warning(f"[FILL_TAG] Redis positions update error: {e}")
    
    # ── 4. MM EXIT GUARD: Track GREATEST_MM INC fills for profit-take watchdog ──
    try:
        source_upper = source.upper() if source else ''
        tag_upper = tag.upper() if tag else ''
        is_greatest_mm = 'GREATEST_MM' in source_upper or 'MM_ENGINE' in source_upper
        # Also catch MM_MM_*_INC tags (Greatest MM format)
        if not is_greatest_mm and tag_upper.startswith('MM_MM_') and 'INC' in tag_upper:
            is_greatest_mm = True
        
        if is_greatest_mm:
            from app.mm.mm_exit_guard import get_mm_exit_guard
            guard = get_mm_exit_guard()
            guard.on_mm_fill(
                symbol=symbol,
                action=action,
                fill_price=0.0,  # Will be updated from actual fill event
                fill_qty=int(abs(fill_qty)),
                account_id=account_id or '',
                tag=tag,
                source=source,
            )
    except Exception as e:
        logger.debug(f"[FILL_TAG] MM Exit Guard notification error: {e}")

    # ── 5. ORDER LIFECYCLE TRACKER ──
    # NOTE: Tracker.on_fill is called directly from hammer_fills_listener.py
    # and ibkr_connector.py where the actual fill_price is available.
    # No call here to avoid double-counting.


def handle_reduce_for_tagging(symbol: str, reduce_qty: float):
    """
    Update PositionTagManager when a position is reduced.
    
    This is called for decrease fills (trim, karbotu, reducemore).
    Priority: Reduces from int_qty first, then ov_qty.
    """
    try:
        from app.psfalgo.position_tags import get_position_tag_manager
        tag_manager = get_position_tag_manager()
        tag_manager.update_on_reduce(symbol, abs(reduce_qty))
        
        new_tag = tag_manager.get_tag(symbol)
        logger.info(f"[FILL_TAG] {symbol}: Reduced by {reduce_qty} → tag={new_tag}")
    except Exception as e:
        logger.debug(f"[FILL_TAG] Reduce tagging error: {e}")


def handle_position_closed(symbol: str, account_id: str = None):
    """
    Clean up POS TAG when position is fully closed (qty → 0).
    Called when current_qty becomes 0 after a fill.
    """
    try:
        from app.psfalgo.position_tag_store import get_position_tag_store
        store = get_position_tag_store()
        if store:
            store.remove_tag(symbol, account_id)
            logger.info(f"[FILL_TAG] {symbol}: Position closed → POS TAG removed ({account_id})")
    except Exception as e:
        logger.debug(f"[FILL_TAG] Position close cleanup error: {e}")
    
    # Also notify MM Exit Guard — stop tracking this fill
    try:
        from app.mm.mm_exit_guard import get_mm_exit_guard
        guard = get_mm_exit_guard()
        guard.on_position_closed(symbol, account_id or '')
    except Exception as e:
        logger.debug(f"[FILL_TAG] MM Exit Guard position close error: {e}")


def get_position_tag(symbol: str) -> str:
    """
    Get current tag for a symbol (legacy).
    
    Returns:
        Tag string like 'LT ov long' or '' if no position
    """
    try:
        from app.psfalgo.position_tags import get_position_tag_manager
        tag_manager = get_position_tag_manager()
        return tag_manager.get_tag(symbol)
    except Exception:
        return ""


def get_position_book(symbol: str, account_id: str = None) -> str:
    """
    Get POS TAG (MM or LT) for a symbol in a specific account.
    
    Uses PositionTagStore (Redis-backed, Dual Tag v4, per-account).
    Fallback: legacy PositionTagManager.
    """
    # Primary: PositionTagStore (Dual Tag v4, per-account)
    try:
        from app.psfalgo.position_tag_store import get_position_tag_store
        store = get_position_tag_store()
        if store:
            return store.get_tag(symbol, account_id)
    except Exception:
        pass
    
    # Fallback: legacy PositionTagManager
    tag = get_position_tag(symbol)
    if 'MM' in tag:
        return 'MM'
    return 'LT'
