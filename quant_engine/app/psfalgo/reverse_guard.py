"""
REVERSE GUARD — Position Reversal Prevention

═══════════════════════════════════════════════════════════════════════════════
RULES:
  1. DECREASE orders cannot flip a position's sign.
  2. Befday > +400 LONG → position cannot go SHORT (TRIM to 0, then BLOCK)
  3. Befday < -400 SHORT → position cannot go LONG (TRIM to 0, then BLOCK)
  4. |Befday| <= 400 → small positions, allowed to flip.
  5. Duplicate open orders → BLOCK if pending already covers position.
═══════════════════════════════════════════════════════════════════════════════

This guard runs JUST BEFORE an order is sent to the broker. It:

1. Reads the CURRENT position qty (from Redis — most up-to-date)
2. Reads ALL OPEN ORDERS for the symbol (from Redis open_orders key)
3. Factors in INTRA-CYCLE approved orders (not yet in Redis open_orders)
4. Calculates EFFECTIVE POTENTIAL = current + pending + intra_cycle_approved
5. Applies reversal protection rules

INTRA-CYCLE TRACKING:
  Within a single cycle, multiple engines may generate orders for the same
  symbol. After the guard approves order #1, it records the impact. When
  order #2 arrives (before Redis updates), the guard sees the ADJUSTED
  effective_potential and correctly BLOCKS the second order.

  Example:
    Order #1 (KARBOTU): SELL 506 → TRIM to 506 (close to 0), recorded
    Order #2 (LT_TRIM): SELL 200 → effective_potential=0 → BLOCKED

Usage:
    from app.psfalgo.reverse_guard import check_reverse_guard, reset_guard_tracking

    # Call at start of each cycle
    reset_guard_tracking()

    # Call before each order
    allowed, adjusted_qty, reason = check_reverse_guard(
        symbol="WAL PRA",
        action="SELL",
        quantity=506,
        tag="MM_KB_LONG_DEC",
        account_id="HAMPRO"
    )
"""

from typing import Tuple, Dict
from loguru import logger


# ═══════════════════════════════════════════════════════════════════════════
# INTRA-CYCLE TRACKING: Track approved orders within current cycle
# ═══════════════════════════════════════════════════════════════════════════
# Key: "{account_id}:{symbol}" → {"sell": total_approved_sell, "buy": total_approved_buy}
_intra_cycle_approved: Dict[str, Dict[str, float]] = {}


def reset_guard_tracking():
    """
    Call at the START of each engine cycle to reset intra-cycle tracking.
    This ensures stale approvals from previous cycles don't affect new orders.
    """
    global _intra_cycle_approved
    _intra_cycle_approved = {}
    logger.debug("[REVERSE_GUARD] Intra-cycle tracking reset")


def _record_approved_order(symbol: str, action: str, quantity: float, account_id: str):
    """Record an approved order for intra-cycle tracking."""
    global _intra_cycle_approved
    key = f"{account_id}:{symbol}"
    if key not in _intra_cycle_approved:
        _intra_cycle_approved[key] = {"sell": 0.0, "buy": 0.0}
    
    if action.upper() == "SELL":
        _intra_cycle_approved[key]["sell"] += quantity
    else:
        _intra_cycle_approved[key]["buy"] += quantity


def _get_intra_cycle_impact(symbol: str, account_id: str) -> Tuple[float, float]:
    """Get intra-cycle approved sell/buy for a symbol. Returns (sell, buy)."""
    key = f"{account_id}:{symbol}"
    entry = _intra_cycle_approved.get(key, {"sell": 0.0, "buy": 0.0})
    return entry["sell"], entry["buy"]


def clear_pending_rev_for_symbol(symbol: str, account_id: str) -> int:
    """
    Clear stale REV order pending state for a symbol.
    
    Called BEFORE sending a fresh REV order to ensure REVERSE GUARD
    sees clean state and allows the new order through.
    
    Clears:
    1. Intra-cycle approved tracking (_intra_cycle_approved)
    2. Redis psfalgo:open_orders:{account} entries matching symbol + REV tag
    
    Returns: count of Redis open_orders entries cleared
    """
    global _intra_cycle_approved
    
    # 1. Clear intra-cycle tracking for this symbol
    key = f"{account_id}:{symbol}"
    if key in _intra_cycle_approved:
        old = _intra_cycle_approved.pop(key)
        logger.info(
            f"[REVERSE_GUARD] 🔄 Cleared intra-cycle for {symbol}: "
            f"sell={old.get('sell', 0):.0f} buy={old.get('buy', 0):.0f} "
            f"Account={account_id}"
        )
    
    # 2. Clear matching REV orders from Redis open_orders
    cleared_count = 0
    try:
        import json
        import time as _time
        from app.core.redis_client import get_redis_client
        redis = get_redis_client()
        if not redis:
            return 0
        
        orders_key = f"psfalgo:open_orders:{account_id}"
        raw = redis.get(orders_key)
        if not raw:
            return 0
        
        data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
        
        # Handle wrapped format vs legacy list
        if isinstance(data, dict) and 'orders' in data:
            orders = data['orders']
            meta = data.get('_meta', {})
        elif isinstance(data, list):
            orders = data
            meta = {}
        else:
            return 0
        
        if not isinstance(orders, list):
            return 0
        
        # Normalize symbol for comparison
        sym_upper = symbol.upper().replace(' ', '')
        
        new_orders = []
        for order in orders:
            order_sym = str(order.get('symbol', '')).upper().replace(' ', '')
            order_tag = str(order.get('strategy_tag', order.get('order_ref', order.get('tag', '')))).upper()
            
            # Match: same symbol AND has REV tag
            if order_sym == sym_upper and 'REV' in order_tag:
                cleared_count += 1
                logger.info(
                    f"[REVERSE_GUARD] 🗑️ Cleared stale REV from Redis: "
                    f"{symbol} {order.get('action', '?')} {order.get('qty', order.get('totalQuantity', '?'))} "
                    f"@ ${order.get('price', order.get('lmtPrice', '?'))} "
                    f"tag={order_tag} Account={account_id}"
                )
            else:
                new_orders.append(order)
        
        if cleared_count > 0:
            meta['updated_at'] = _time.time()
            meta['cleared_by'] = 'rev_refresh'
            payload = {'orders': new_orders, '_meta': meta}
            redis.set(orders_key, json.dumps(payload), ex=600)
            logger.info(
                f"[REVERSE_GUARD] ✅ Cleared {cleared_count} stale REV entries "
                f"for {symbol} from Redis open_orders ({account_id})"
            )
    except Exception as e:
        logger.warning(f"[REVERSE_GUARD] clear_pending_rev_for_symbol error: {e}")
    
    return cleared_count


def check_reverse_guard(
    symbol: str,
    action: str,
    quantity: float,
    tag: str,
    account_id: str,
) -> Tuple[bool, float, str]:
    """
    Final guard before order is sent to broker.
    
    Returns:
        (allowed, adjusted_qty, reason)
        - allowed: True if order can proceed
        - adjusted_qty: Possibly reduced qty to prevent reversal
        - reason: Human-readable explanation
    """
    try:
        import json
        from app.core.redis_client import get_redis_client
        redis = get_redis_client()
        if not redis:
            return True, quantity, "NO_REDIS"
        
        action_upper = action.upper()
        
        # ═══════════════════════════════════════════════════════════════
        # STEP 1: Get CURRENT position qty (freshest from Redis)
        # ═══════════════════════════════════════════════════════════════
        current_qty = _get_current_qty(redis, symbol, account_id)
        
        # ═══════════════════════════════════════════════════════════════
        # STEP 2: Get BEFDAY qty
        # ═══════════════════════════════════════════════════════════════
        befday_qty = _get_befday_qty(redis, symbol, account_id)
        
        # ═══════════════════════════════════════════════════════════════
        # STEP 3: Get pending OPEN ORDERS (from Redis) + intra-cycle
        # ═══════════════════════════════════════════════════════════════
        pending_sell, pending_buy = _get_pending_orders(redis, symbol, account_id)
        
        # Add intra-cycle approved orders (not yet in Redis)
        intra_sell, intra_buy = _get_intra_cycle_impact(symbol, account_id)
        total_pending_sell = pending_sell + intra_sell
        total_pending_buy = pending_buy + intra_buy
        
        # Net pending impact on position
        net_pending = total_pending_buy - total_pending_sell
        
        # Effective potential WITH existing open orders + intra-cycle
        effective_potential = current_qty + net_pending
        
        # ═══════════════════════════════════════════════════════════════
        # STEP 4: Calculate what THIS order would do
        # ═══════════════════════════════════════════════════════════════
        if action_upper == 'SELL':
            order_impact = -quantity
        else:
            order_impact = quantity
        
        new_potential = effective_potential + order_impact
        
        # ═══════════════════════════════════════════════════════════════
        # RULE 1: Detect if tag is DECREASE
        # ═══════════════════════════════════════════════════════════════
        tag_upper = (tag or '').upper()
        is_decrease = any(kw in tag_upper for kw in [
            'DEC', 'REDUCE', 'TRIM', 'KARBOTU', 'KB_LONG', 'KB_SHORT',
            'REDUCEMORE', 'REV_TP', 'REV_RL'
        ])
        
        # ═══════════════════════════════════════════════════════════════
        # RULE 2: DUPLICATE ORDER CHECK — open orders already cover it
        # ═══════════════════════════════════════════════════════════════
        if is_decrease:
            if action_upper == 'SELL' and total_pending_sell >= abs(current_qty) and current_qty > 0:
                logger.warning(
                    f"[REVERSE_GUARD] ⛔ DUPLICATE BLOCKED: {symbol} SELL {quantity:.0f} "
                    f"| current={current_qty:.0f} but pending_sell={total_pending_sell:.0f} "
                    f"(redis={pending_sell:.0f}+intra={intra_sell:.0f}) "
                    f"already covers position. Account={account_id}"
                )
                return False, 0, f"DUPLICATE_SELL_BLOCKED(pending={total_pending_sell:.0f}>=pos={current_qty:.0f})"
            
            if action_upper == 'BUY' and total_pending_buy >= abs(current_qty) and current_qty < 0:
                logger.warning(
                    f"[REVERSE_GUARD] ⛔ DUPLICATE BLOCKED: {symbol} BUY {quantity:.0f} "
                    f"| current={current_qty:.0f} but pending_buy={total_pending_buy:.0f} "
                    f"(redis={pending_buy:.0f}+intra={intra_buy:.0f}) "
                    f"already covers position. Account={account_id}"
                )
                return False, 0, f"DUPLICATE_BUY_BLOCKED(pending={total_pending_buy:.0f}>=pos={abs(current_qty):.0f})"
        
        # ═══════════════════════════════════════════════════════════════
        # RULE 3: DECREASE REVERSE PROTECTION — cannot flip sign
        # ═══════════════════════════════════════════════════════════════
        if is_decrease:
            # LONG position: SELL cannot make potential < 0
            if current_qty > 0 and action_upper == 'SELL':
                if new_potential < 0:
                    # TRIM: bring to 0 (not below)
                    max_sell = max(0, effective_potential)
                    if max_sell < 1:
                        logger.warning(
                            f"[REVERSE_GUARD] ⛔ REVERSE BLOCKED: {symbol} SELL {quantity:.0f} "
                            f"| current={current_qty:.0f} eff_potential={effective_potential:.0f} "
                            f"pending_sell={total_pending_sell:.0f} → would_be={new_potential:.0f} < 0! "
                            f"Account={account_id} tag={tag}"
                        )
                        return False, 0, f"REVERSE_BLOCKED(eff={effective_potential:.0f},would={new_potential:.0f})"
                    else:
                        logger.warning(
                            f"[REVERSE_GUARD] ✂️ REVERSE TRIMMED to 0: {symbol} SELL {quantity:.0f} → {max_sell:.0f} "
                            f"| current={current_qty:.0f} eff_potential={effective_potential:.0f} "
                            f"pending_sell={total_pending_sell:.0f} Account={account_id} tag={tag}"
                        )
                        _record_approved_order(symbol, action_upper, max_sell, account_id)
                        return True, max_sell, f"REVERSE_TRIMMED({quantity:.0f}->{max_sell:.0f})"
            
            # SHORT position: BUY cannot make potential > 0
            if current_qty < 0 and action_upper == 'BUY':
                if new_potential > 0:
                    max_buy = max(0, abs(effective_potential))
                    if max_buy < 1:
                        logger.warning(
                            f"[REVERSE_GUARD] ⛔ REVERSE BLOCKED: {symbol} BUY {quantity:.0f} "
                            f"| current={current_qty:.0f} eff_potential={effective_potential:.0f} "
                            f"pending_buy={total_pending_buy:.0f} → would_be={new_potential:.0f} > 0! "
                            f"Account={account_id} tag={tag}"
                        )
                        return False, 0, f"REVERSE_BLOCKED(eff={effective_potential:.0f},would={new_potential:.0f})"
                    else:
                        logger.warning(
                            f"[REVERSE_GUARD] ✂️ REVERSE TRIMMED to 0: {symbol} BUY {quantity:.0f} → {max_buy:.0f} "
                            f"| current={current_qty:.0f} eff_potential={effective_potential:.0f} "
                            f"pending_buy={total_pending_buy:.0f} Account={account_id} tag={tag}"
                        )
                        _record_approved_order(symbol, action_upper, max_buy, account_id)
                        return True, max_buy, f"REVERSE_TRIMMED({quantity:.0f}->{max_buy:.0f})"
        
        # ═══════════════════════════════════════════════════════════════
        # RULE 4: BEFDAY REVERSAL PROTECTION (ALL engines, not just DEC)
        # ═══════════════════════════════════════════════════════════════
        # KURAL: Buyuk pozisyonlar (|befday| > 400) terse gecemez.
        #   - befday > +400 (LONG)  → new_potential SHORT olamaz → TRIM to 0
        #   - befday < -400 (SHORT) → new_potential LONG olamaz  → TRIM to 0
        # Kucuk pozisyonlar (|befday| <= 400) flip yapabilir.
        REVERSAL_THRESHOLD = 400
        
        if befday_qty > REVERSAL_THRESHOLD and new_potential < 0:
            # LONG befday > 400 lots → cannot go SHORT → TRIM to 0
            max_allowed = max(0, effective_potential)
            if max_allowed < 1:
                # effective_potential already 0 or negative → BLOCK
                logger.error(
                    f"[REVERSE_GUARD] ⛔ BEFDAY REVERSAL BLOCKED: {symbol} {action_upper} {quantity:.0f} "
                    f"| befday={befday_qty:.0f} (LONG>{REVERSAL_THRESHOLD}) current={current_qty:.0f} "
                    f"eff_potential={effective_potential:.0f} → would_be={new_potential:.0f} (SHORT!) "
                    f"Account={account_id} tag={tag}"
                )
                return False, 0, f"BEFDAY_REVERSAL_BLOCKED(befday={befday_qty:.0f},eff={effective_potential:.0f})"
            else:
                # TRIM to bring position to 0 (not below)
                logger.warning(
                    f"[REVERSE_GUARD] ✂️ BEFDAY REVERSAL TRIMMED to 0: {symbol} {action_upper} {quantity:.0f} → {max_allowed:.0f} "
                    f"| befday={befday_qty:.0f} (LONG>{REVERSAL_THRESHOLD}) current={current_qty:.0f} "
                    f"eff_potential={effective_potential:.0f} Account={account_id} tag={tag}"
                )
                _record_approved_order(symbol, action_upper, max_allowed, account_id)
                return True, max_allowed, f"BEFDAY_REVERSAL_TRIMMED({quantity:.0f}->{max_allowed:.0f})"
        
        if befday_qty < -REVERSAL_THRESHOLD and new_potential > 0:
            # SHORT befday > 400 lots → cannot go LONG → TRIM to 0
            max_allowed = max(0, abs(effective_potential))
            if max_allowed < 1:
                # effective_potential already 0 or positive → BLOCK
                logger.error(
                    f"[REVERSE_GUARD] ⛔ BEFDAY REVERSAL BLOCKED: {symbol} {action_upper} {quantity:.0f} "
                    f"| befday={befday_qty:.0f} (SHORT>{REVERSAL_THRESHOLD}) current={current_qty:.0f} "
                    f"eff_potential={effective_potential:.0f} → would_be={new_potential:.0f} (LONG!) "
                    f"Account={account_id} tag={tag}"
                )
                return False, 0, f"BEFDAY_REVERSAL_BLOCKED(befday={befday_qty:.0f},eff={effective_potential:.0f})"
            else:
                # TRIM to bring position to 0 (not below)
                logger.warning(
                    f"[REVERSE_GUARD] ✂️ BEFDAY REVERSAL TRIMMED to 0: {symbol} {action_upper} {quantity:.0f} → {max_allowed:.0f} "
                    f"| befday={befday_qty:.0f} (SHORT>{REVERSAL_THRESHOLD}) current={current_qty:.0f} "
                    f"eff_potential={effective_potential:.0f} Account={account_id} tag={tag}"
                )
                _record_approved_order(symbol, action_upper, max_allowed, account_id)
                return True, max_allowed, f"BEFDAY_REVERSAL_TRIMMED({quantity:.0f}->{max_allowed:.0f})"
        
        # ═══════════════════════════════════════════════════════════════
        # ALL CHECKS PASSED — Record and allow
        # ═══════════════════════════════════════════════════════════════
        _record_approved_order(symbol, action_upper, quantity, account_id)
        return True, quantity, "OK"
        
    except Exception as e:
        logger.error(f"[REVERSE_GUARD] Error checking {symbol}: {e}", exc_info=True)
        return True, quantity, f"ERROR({e})"


# ═══════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS — Redis data readers
# ═══════════════════════════════════════════════════════════════════════════

def _get_current_qty(redis, symbol: str, account_id: str) -> float:
    """Get current position qty from Redis."""
    import json
    try:
        for acct_key in [account_id, account_id.upper()]:
            raw = redis.get(f"psfalgo:positions:{acct_key}")
            if raw:
                data = json.loads(raw)
                # Direct match
                if symbol in data:
                    entry = data[symbol]
                    if isinstance(entry, dict):
                        return float(entry.get('qty', 0))
                    return float(entry)
                # Fuzzy match on display_symbol
                for sym, details in data.items():
                    if sym == '_meta':
                        continue
                    if isinstance(details, dict):
                        if details.get('symbol') == symbol or details.get('display_symbol') == symbol:
                            return float(details.get('qty', 0))
    except Exception as e:
        logger.debug(f"[REVERSE_GUARD] _get_current_qty error: {e}")
    return 0.0


def _get_befday_qty(redis, symbol: str, account_id: str) -> float:
    """Get befday position qty from Redis."""
    import json
    try:
        # Source 1: psfalgo:befday:{account}
        raw = redis.get(f"psfalgo:befday:{account_id}")
        if raw:
            data = json.loads(raw)
            if symbol in data:
                val = data[symbol]
                if isinstance(val, dict):
                    return float(val.get('qty', val.get('befday_qty', 0)))
                return float(val)
        
        # Source 2: befday_qty inside psfalgo:positions:{account}
        raw2 = redis.get(f"psfalgo:positions:{account_id}")
        if raw2:
            data2 = json.loads(raw2)
            if symbol in data2 and isinstance(data2[symbol], dict):
                bq = data2[symbol].get('befday_qty', 0)
                if bq:
                    return float(bq)
            # Fuzzy match
            for sym, details in data2.items():
                if sym == '_meta':
                    continue
                if isinstance(details, dict):
                    if details.get('symbol') == symbol or details.get('display_symbol') == symbol:
                        bq = details.get('befday_qty', 0)
                        if bq:
                            return float(bq)
    except Exception as e:
        logger.debug(f"[REVERSE_GUARD] _get_befday_qty error: {e}")
    return 0.0


def _get_pending_orders(redis, symbol: str, account_id: str) -> Tuple[float, float]:
    """
    Get total pending SELL and BUY quantities for a symbol from open orders.
    
    Returns: (total_pending_sell, total_pending_buy)
    """
    import json
    total_sell = 0.0
    total_buy = 0.0
    
    try:
        raw = redis.get(f"psfalgo:open_orders:{account_id}")
        if not raw:
            return 0.0, 0.0
        
        data = json.loads(raw)
        if isinstance(data, dict) and 'orders' in data:
            orders = data['orders']
        elif isinstance(data, list):
            orders = data
        else:
            return 0.0, 0.0
        
        # Normalize symbol for comparison
        sym_upper = symbol.upper().replace(' ', '')
        
        for order in orders:
            order_sym = str(order.get('symbol', '')).upper().replace(' ', '')
            # Also try Hammer format matching (e.g. WALPRA vs WAL PRA)
            order_sym_h = order_sym.replace('PR', ' PR').strip().replace(' ', '')
            
            if order_sym == sym_upper or order_sym_h == sym_upper:
                qty = float(order.get('totalQuantity', order.get('qty', order.get('quantity', 0))))
                act = str(order.get('action', '')).upper()
                
                if act == 'SELL':
                    total_sell += qty
                elif act == 'BUY':
                    total_buy += qty
    except Exception as e:
        logger.debug(f"[REVERSE_GUARD] _get_pending_orders error: {e}")
    
    return total_sell, total_buy
