"""
Order Context Logger — Merkezi emir bağlam bilgisi toplayan helper.

Her emir gönderiminde (sent) ve her fill'de kullanılır.
FBtot, SFStot, GORT, PFF, Bid/Ask, Volav bilgilerini tek yerden çeker.
"""

from typing import Optional, Dict, Any
from app.core.logger import logger


def get_order_context(symbol: str, fill_time: Optional[str] = None) -> Dict[str, Any]:
    """
    Get all metrics for a symbol at the current moment (or at fill_time for recovery fills).
    
    Args:
        symbol: The ticker symbol
        fill_time: Optional HH:MM:SS or IBKR format timestamp for historical fills.
                   When provided, PFF is fetched at that historical time.
                   FBtot/SFStot/GORT are still current (historical not stored).
    
    Returns dict with keys:
        fbtot, sfstot, gort, pff, bid, ask, spread, group, volav, volav_window,
        truth_tick, is_historical
    All values may be None if data unavailable.
    
    Data sources (in priority order):
        1. MarketSnapshotStore (IBKR_PED → IBKR_GUN)
        2. JanallMetricsEngine symbol_metrics_cache (most reliable for FBtot/SFStot/GORT)
        3. market_data_cache (RAM — bid/ask/last from DataFabric sync)
        4. Redis market:l1:{symbol} (L1 Feed Worker)
        5. Hammer L1 live ticks (direct API)
    """
    ctx: Dict[str, Any] = {
        'fbtot': None,
        'sfstot': None,
        'gort': None,
        'pff': None,
        'bid': None,
        'ask': None,
        'last': None,
        'spread': None,
        'group': None,
        'volav': None,
        'volav_window': None,
        'truth_tick': None,
        'tt1': None,  # Latest truth tick price
        'tt2': None,  # 2nd latest truth tick price
        'tt3': None,  # 3rd latest truth tick price
        'is_historical': fill_time is not None
    }
    
    try:
        # ══════════════════════════════════════════════════════════════
        # SOURCE 1: MarketSnapshotStore (computed metrics + L1)
        # ══════════════════════════════════════════════════════════════
        from app.psfalgo.market_snapshot_store import get_market_snapshot_store
        store = get_market_snapshot_store()
        if store:
            snapshot = store.get_current_snapshot(symbol, 'IBKR_PED')
            if not snapshot:
                snapshot = store.get_current_snapshot(symbol, 'IBKR_GUN')
            if snapshot:
                ctx['fbtot'] = snapshot.fbtot
                ctx['sfstot'] = snapshot.sfstot
                ctx['gort'] = snapshot.gort
                if snapshot.bid:
                    ctx['bid'] = snapshot.bid
                if snapshot.ask:
                    ctx['ask'] = snapshot.ask
                if getattr(snapshot, 'last', None):
                    ctx['last'] = snapshot.last
                if snapshot.spread:
                    ctx['spread'] = snapshot.spread
        
        # ══════════════════════════════════════════════════════════════
        # SOURCE 2: JanallMetricsEngine cache (MOST RELIABLE for metrics)
        # This is the same cache RUNALL uses for GORT/FBtot enrichment
        # ══════════════════════════════════════════════════════════════
        if ctx['fbtot'] is None or ctx['sfstot'] is None or ctx['gort'] is None:
            try:
                from app.api.market_data_routes import get_janall_metrics_engine as get_janall_from_api
                janall_engine = get_janall_from_api()
                if janall_engine and hasattr(janall_engine, 'symbol_metrics_cache'):
                    janall_data = janall_engine.symbol_metrics_cache.get(symbol, {})
                    if janall_data:
                        if ctx['fbtot'] is None:
                            ctx['fbtot'] = janall_data.get('fbtot')
                        if ctx['sfstot'] is None:
                            ctx['sfstot'] = janall_data.get('sfstot')
                        if ctx['gort'] is None:
                            ctx['gort'] = janall_data.get('gort')
                        # Also get bid/ask from Janall breakdown if missing
                        if ctx['bid'] is None or ctx['ask'] is None:
                            breakdown = janall_data.get('_breakdown', {})
                            inputs = breakdown.get('inputs', {})
                            if ctx['bid'] is None and inputs.get('bid'):
                                ctx['bid'] = inputs['bid']
                            if ctx['ask'] is None and inputs.get('ask'):
                                ctx['ask'] = inputs['ask']
                            if ctx['last'] is None and inputs.get('last'):
                                ctx['last'] = inputs['last']
            except Exception:
                pass
        
        # ══════════════════════════════════════════════════════════════
        # SOURCE 3: market_data_cache (RAM — synced by RUNALL each cycle)
        # ══════════════════════════════════════════════════════════════
        if ctx['bid'] is None or ctx['ask'] is None:
            try:
                from app.api.market_data_routes import market_data_cache
                mdc = market_data_cache.get(symbol, {})
                if mdc:
                    if ctx['bid'] is None and mdc.get('bid'):
                        ctx['bid'] = mdc['bid']
                    if ctx['ask'] is None and mdc.get('ask'):
                        ctx['ask'] = mdc['ask']
                    if ctx['last'] is None and mdc.get('last'):
                        ctx['last'] = mdc['last']
            except Exception:
                pass
        
        # ══════════════════════════════════════════════════════════════
        # SOURCE 4: Redis L1 keys (from L1 Feed Worker)
        # ══════════════════════════════════════════════════════════════
        if ctx['bid'] is None or ctx['ask'] is None:
            try:
                import json
                from app.core.redis_client import get_redis
                from app.live.symbol_mapper import SymbolMapper
                r = get_redis()
                if r:
                    # 🔑 TICKER CONVENTION: Try both Hammer and PREF_IBKR formats
                    hammer_sym = SymbolMapper.to_hammer_symbol(symbol)
                    display_sym = SymbolMapper.to_display_symbol(symbol)
                    for sym in dict.fromkeys([symbol, hammer_sym, display_sym]):
                        raw = r.get(f"market:l1:{sym}")
                        if raw:
                            l1 = json.loads(raw)
                            if ctx['bid'] is None and l1.get('bid'):
                                ctx['bid'] = l1['bid']
                            if ctx['ask'] is None and l1.get('ask'):
                                ctx['ask'] = l1['ask']
                            if ctx['last'] is None and l1.get('last'):
                                ctx['last'] = l1['last']
                            if ctx['bid'] is not None and ctx['ask'] is not None:
                                break
            except Exception:
                pass
        
        # ══════════════════════════════════════════════════════════════
        # SOURCE 5: Hammer L1 live ticks (direct API — last resort)
        # ══════════════════════════════════════════════════════════════
        if ctx['bid'] is None or ctx['ask'] is None:
            try:
                from app.live.hammer_client import get_hammer_client
                hc = get_hammer_client()
                if hc and hc.is_connected():
                    ticks = hc.get_ticks(symbol)
                    if ticks:
                        if ctx['bid'] is None:
                            ctx['bid'] = ticks.get('bid')
                        if ctx['ask'] is None:
                            ctx['ask'] = ticks.get('ask')
            except Exception:
                pass
        
        # Compute spread from bid/ask if missing
        if ctx['spread'] is None and ctx['bid'] and ctx['ask']:
            if ctx['ask'] > ctx['bid']:
                ctx['spread'] = round(ctx['ask'] - ctx['bid'], 4)
        
        # ══════════════════════════════════════════════════════════════
        # PFF price (historical if fill_time provided)
        # ══════════════════════════════════════════════════════════════
        try:
            from app.trading.daily_fills_store import get_daily_fills_store
            fills_store = get_daily_fills_store()
            if fills_store:
                ctx['pff'] = fills_store._fetch_pff_price(fill_time=fill_time)
        except Exception:
            pass
        
        # ══════════════════════════════════════════════════════════════
        # Group info
        # ══════════════════════════════════════════════════════════════
        try:
            from app.market_data.grouping import resolve_primary_group
            ctx['group'] = resolve_primary_group({}, symbol)
        except Exception:
            pass
        
        # ══════════════════════════════════════════════════════════════
        # Volav (Redis first → tick_store fallback)
        # CRITICAL: Worker process writes fresh Volav to Redis every 60s.
        # Backend tick_store is STALE (only loaded at startup).
        # ══════════════════════════════════════════════════════════════
        try:
            volav_price, volav_win = _fetch_volav_for_symbol(symbol)
            ctx['volav'] = volav_price
            ctx['volav_window'] = volav_win
        except Exception:
            pass
        
        # ══════════════════════════════════════════════════════════════
        # TRUTH TICK DATA — tt1, tt2, tt3 (last 3 truth ticks)
        # 
        # PRIORITY ORDER (fixed 2026-03-19):
        #   1. tt:ticks:{symbol} from Redis — SAME source as lifecycle_tracker
        #      Worker persists ticks here. Newest tick at END of list.
        #   2. truthtick:latest:{symbol} — Worker inspect output (secondary)
        #   3. In-memory tick_store — LAST RESORT (main process only has
        #      startup data, NOT the worker's live ticks)
        #
        # ⚠️ ALL sources use 24h staleness check on tick TIMESTAMP (not updated_at)
        # ══════════════════════════════════════════════════════════════
        try:
            import json as _json_tt
            import time as _time_tt
            from app.core.redis_client import get_redis
            STALENESS_LIMIT = 86400  # 24 hours in seconds
            now_ts = _time_tt.time()
            
            from app.live.symbol_mapper import SymbolMapper as _SM_tt
            _h_tt = _SM_tt.to_hammer_symbol(symbol)
            _d_tt = _SM_tt.to_display_symbol(symbol)
            r = get_redis()
            
            # ─── SOURCE 1: tt:ticks:{symbol} (PRIMARY — same as lifecycle tracker) ───
            if r and ctx['tt1'] is None:
                try:
                    for _sym_tt in dict.fromkeys([symbol, _h_tt, _d_tt]):
                        raw_ticks = r.get(f"tt:ticks:{_sym_tt}")
                        if raw_ticks:
                            all_ticks = _json_tt.loads(raw_ticks)
                            if all_ticks and len(all_ticks) > 0:
                                valid = []
                                for t in reversed(all_ticks):
                                    tick_ts = t.get('ts', 0)
                                    if tick_ts > 0 and (now_ts - tick_ts) > STALENESS_LIMIT:
                                        continue  # STALE — skip
                                    price = t.get('price', 0)
                                    if price > 0:
                                        valid.append(t)
                                    if len(valid) >= 3:
                                        break
                                
                                if len(valid) >= 1:
                                    ctx['tt1'] = valid[0].get('price')
                                    ctx['truth_tick'] = ctx['tt1']
                                if len(valid) >= 2:
                                    ctx['tt2'] = valid[1].get('price')
                                if len(valid) >= 3:
                                    ctx['tt3'] = valid[2].get('price')
                                if valid:
                                    break
                except Exception:
                    pass
            
            # ─── SOURCE 2: truthtick:latest:{symbol} (Worker inspect output) ───
            if r and ctx['tt1'] is None:
                try:
                    for _sym_tt in dict.fromkeys([symbol, _h_tt, _d_tt]):
                        raw_tt = r.get(f"truthtick:latest:{_sym_tt}")
                        if raw_tt:
                            tt_data = _json_tt.loads(raw_tt)
                            tt_price = tt_data.get('price')
                            # Use tick timestamp for staleness, NOT updated_at
                            tt_ts = tt_data.get('ts', 0)
                            if tt_price and tt_ts > 0 and (now_ts - tt_ts) <= STALENESS_LIMIT:
                                ctx['truth_tick'] = tt_price
                                ctx['tt1'] = tt_price
                                break
                except Exception:
                    pass
            
            # ─── SOURCE 3: In-memory tick_store (LAST RESORT) ───
            # NOTE: In main process, tick_store only has startup data from
            # restore_from_redis. Worker's fresh ticks are NOT here.
            if ctx['tt1'] is None:
                try:
                    from app.market_data.truth_ticks_engine import get_truth_ticks_engine
                    tt_engine = get_truth_ticks_engine()
                    if tt_engine:
                        with tt_engine._tick_lock:
                            ticks = tt_engine.tick_store.get(symbol)
                            if ticks and len(ticks) > 0:
                                valid_ticks = []
                                for t in reversed(list(ticks)):
                                    tick_ts = t.get('ts', 0)
                                    if tick_ts > 0 and (now_ts - tick_ts) > STALENESS_LIMIT:
                                        continue  # STALE — skip
                                    price = t.get('price', 0)
                                    if price > 0:
                                        valid_ticks.append(t)
                                    if len(valid_ticks) >= 3:
                                        break
                                
                                if len(valid_ticks) >= 1:
                                    ctx['tt1'] = valid_ticks[0].get('price')
                                    ctx['truth_tick'] = ctx['tt1']
                                if len(valid_ticks) >= 2:
                                    ctx['tt2'] = valid_ticks[1].get('price')
                                if len(valid_ticks) >= 3:
                                    ctx['tt3'] = valid_ticks[2].get('price')
                except Exception:
                    pass
        except Exception:
            pass
        
    except Exception as e:
        logger.debug(f"[ORDER_CONTEXT] Error getting context for {symbol}: {e}")
    
    return ctx


def _fetch_volav_for_symbol(symbol: str):
    """
    Fetch Volav1 price for a symbol.
    Returns (volav_price, window) where window is '1h' or '4h'.
    Returns (None, None) if unavailable.
    
    CRITICAL: Uses 2-phase lookup:
      1. PRIMARY: Redis truth_ticks:inspect:{symbol} (Worker updates every 60s)
         Contains pre-computed volav_details with fresh trade data.
      2. FALLBACK: Redis tt:ticks:{symbol} → compute locally
         Only used if inspect data unavailable.
    
    Backend's tick_store is NOT used as primary source because it is 
    only loaded at process startup (restore_from_redis) and becomes stale.
    """
    try:
        import time
        import json
        
        # ══════════════════════════════════════════════════════════════
        # PRIMARY: Redis truth_ticks:inspect:{symbol}
        # Written by Worker's Analysis Scheduler every 60 seconds.
        # Contains pre-computed Volav levels from FRESH trade data.
        # ══════════════════════════════════════════════════════════════
        try:
            from app.core.redis_client import get_redis
            r = get_redis()
            if r:
                raw_inspect = r.get(f"truth_ticks:inspect:{symbol}")
                if raw_inspect:
                    inspect_data = json.loads(raw_inspect)
                    data = inspect_data.get('data', {})
                    volav_details = data.get('volav_details', {})
                    volavs = volav_details.get('volavs', [])
                    
                    if volavs and len(volavs) > 0:
                        volav1_price = volavs[0].get('price')
                        if volav1_price:
                            # Determine window from temporal_analysis
                            temporal = data.get('temporal_analysis', {})
                            # Check 1h first, then 4h
                            if temporal.get('1h', {}).get('change') is not None:
                                return volav1_price, '1h'
                            elif temporal.get('4h', {}).get('change') is not None:
                                return volav1_price, '4h'
                            else:
                                return volav1_price, '1h'  # Default window label
        except Exception:
            pass
        
        # ══════════════════════════════════════════════════════════════
        # FALLBACK: Redis tt:ticks:{symbol} → compute locally
        # This data is persisted by Worker every 500 ticks (12-day TTL).
        # Better than backend's tick_store which is only startup-loaded.
        # ══════════════════════════════════════════════════════════════
        ticks = None
        try:
            from app.core.redis_client import get_redis
            r = get_redis()
            if r:
                raw = r.get(f"tt:ticks:{symbol}")
                if raw:
                    ticks = json.loads(raw)
        except Exception:
            pass
        
        # LAST RESORT: Backend tick_store (may be stale)
        if not ticks:
            try:
                from app.market_data.truth_ticks_engine import get_truth_ticks_engine
                tt_engine = get_truth_ticks_engine()
                if tt_engine:
                    with tt_engine._tick_lock:
                        if symbol in tt_engine.tick_store and len(tt_engine.tick_store[symbol]) > 0:
                            ticks = list(tt_engine.tick_store[symbol])
            except Exception:
                pass
        
        if not ticks or len(ticks) < 3:
            return None, None
        
        # Get avg_adv for proper volav computation
        avg_adv = 0.0
        try:
            from app.psfalgo.market_snapshot_store import get_market_snapshot_store
            store = get_market_snapshot_store()
            if store:
                snap = store.get_current_snapshot(symbol, 'IBKR_PED')
                if not snap:
                    snap = store.get_current_snapshot(symbol, 'IBKR_GUN')
                if snap:
                    avg_adv = float(getattr(snap, 'avg_adv', 0) or 0)
        except Exception:
            pass
        
        now = time.time()
        
        # Try 1h window first
        ONE_HOUR = 3600
        ticks_window = [t for t in ticks if (now - t.get('ts', 0)) <= ONE_HOUR]
        volav_window = '1h'
        
        # Fallback to 4h
        if len(ticks_window) < 3:
            FOUR_HOURS = 4 * 3600
            ticks_window = [t for t in ticks if (now - t.get('ts', 0)) <= FOUR_HOURS]
            volav_window = '4h'
        
        if not ticks_window:
            return None, None
        
        from app.market_data.truth_ticks_engine import get_truth_ticks_engine
        tt_engine = get_truth_ticks_engine()
        if not tt_engine:
            return None, None
        
        volav_levels, _ = tt_engine.compute_volav_levels(
            truth_ticks=ticks_window, top_n=4, avg_adv=avg_adv
        )
        if volav_levels:
            price = volav_levels[0].get('price')
            if price:
                return price, volav_window
    except Exception as e:
        logger.debug(f"[ORDER_CONTEXT] Volav fetch error for {symbol}: {e}")
    return None, None


def _format_volav(ctx: Dict[str, Any]) -> str:
    """Format Volav string from context. Returns '' if no volav."""
    if ctx.get('volav') and ctx.get('volav_window'):
        return f"Volav_{ctx['volav_window']}=${ctx['volav']:.2f}"
    return ""


def format_order_sent_log(
    symbol: str,
    action: str,
    quantity: int,
    price: float,
    tag: str,
    account_id: str,
    engine_source: str = "",
    ctx: Optional[Dict[str, Any]] = None
) -> str:
    """Format a comprehensive order-sent log line."""
    if ctx is None:
        ctx = get_order_context(symbol)
    
    parts = [
        f"📤 [ORDER_SENT] {symbol} {action} {quantity} @ ${price:.2f}",
        f"Tag: {tag}",
        f"Account: {account_id}",
    ]
    
    if engine_source:
        parts.insert(1, f"Engine: {engine_source}")
    
    # Bid/Ask/Last
    bid_str = f"${ctx['bid']:.2f}" if ctx.get('bid') else "N/A"
    ask_str = f"${ctx['ask']:.2f}" if ctx.get('ask') else "N/A"
    parts.append(f"Bid: {bid_str} Ask: {ask_str}")
    
    # PFF
    if ctx.get('pff'):
        parts.append(f"PFF@sent: ${ctx['pff']:.2f}")
    
    # Metrics (FBtot, SFStot, GORT)
    metrics = []
    if ctx.get('fbtot') is not None:
        metrics.append(f"FBtot={ctx['fbtot']:.2f}")
    if ctx.get('sfstot') is not None:
        metrics.append(f"SFStot={ctx['sfstot']:.2f}")
    if ctx.get('gort') is not None:
        metrics.append(f"GORT={ctx['gort']:.2f}")
    if metrics:
        parts.append(" ".join(metrics))
    
    if ctx.get('group'):
        parts.append(f"Group: {ctx['group']}")
    
    # Volav
    volav_str = _format_volav(ctx)
    if volav_str:
        parts.append(volav_str)
    
    # Truth Ticks (tt1=latest, tt2=previous, tt3=third)
    tt_parts = []
    if ctx.get('tt1') is not None:
        tt_parts.append(f"tt1=${ctx['tt1']:.2f}")
    if ctx.get('tt2') is not None:
        tt_parts.append(f"tt2=${ctx['tt2']:.2f}")
    if ctx.get('tt3') is not None:
        tt_parts.append(f"tt3=${ctx['tt3']:.2f}")
    if tt_parts:
        parts.append(" ".join(tt_parts))
    elif ctx.get('truth_tick') is not None:
        parts.append(f"TT=${ctx['truth_tick']:.2f}")
    
    return " | ".join(parts)


def format_fill_log(
    symbol: str,
    action: str,
    qty: float,
    price: float,
    tag: str,
    bid: Optional[float] = None,
    ask: Optional[float] = None,
    pff_price: Optional[float] = None,
    bench_source: Optional[str] = None,
    ctx: Optional[Dict[str, Any]] = None,
    fill_time: Optional[str] = None
) -> str:
    """Format a comprehensive fill log line."""
    if ctx is None:
        ctx = get_order_context(symbol, fill_time=fill_time)
    
    # Determine position change type from tag
    tag_upper = tag.upper() if tag else ""
    if any(k in tag_upper for k in ['_INC', 'LONG_INC', 'SHORT_INC', 'MM_LONG', 'MM_SHORT']):
        pos_type = "POS_INC 📈"
    elif any(k in tag_upper for k in ['_DEC', 'LONG_DEC', 'SHORT_DEC']):
        pos_type = "POS_DEC 📉"
    else:
        pos_type = "UNKNOWN"
    
    # Historical marker for offline/recovery fills
    hist_marker = " [HIST]" if ctx.get('is_historical') else ""
    
    parts = [
        f"✅ [FILL]{hist_marker} {symbol} {action} {qty} @ ${price:.2f}",
        f"Tag: {tag}",
        f"Type: {pos_type}",
    ]
    
    # Bid/Ask (prefer passed values, fallback to context)
    b = bid if bid else ctx.get('bid')
    a = ask if ask else ctx.get('ask')
    bid_str = f"${b:.2f}" if b else "N/A"
    ask_str = f"${a:.2f}" if a else "N/A"
    ba_label = "Bid" if not ctx.get('is_historical') else "Bid[LIVE]"
    parts.append(f"{ba_label}: {bid_str} Ask: {ask_str}")
    
    # PFF (historical PFF is accurate when fill_time provided)
    pff = pff_price if pff_price else ctx.get('pff')
    if pff:
        pff_label = "PFF@fill" if not ctx.get('is_historical') else "PFF@fill[HIST]"
        parts.append(f"{pff_label}: ${pff:.2f}")
    
    # Metrics (always live — historical not stored)
    metrics = []
    metric_suffix = "" if not ctx.get('is_historical') else "[LIVE]"
    if ctx.get('fbtot') is not None:
        metrics.append(f"FBtot{metric_suffix}={ctx['fbtot']:.2f}")
    if ctx.get('sfstot') is not None:
        metrics.append(f"SFStot{metric_suffix}={ctx['sfstot']:.2f}")
    if ctx.get('gort') is not None:
        metrics.append(f"GORT{metric_suffix}={ctx['gort']:.2f}")
    if metrics:
        parts.append(" ".join(metrics))
    
    group = bench_source or ctx.get('group')
    if group:
        parts.append(f"Group: {group}")
    
    # Volav
    volav_str = _format_volav(ctx)
    if volav_str:
        parts.append(volav_str)
    
    # Truth Ticks (tt1=latest, tt2=previous, tt3=third)
    tt_parts = []
    if ctx.get('tt1') is not None:
        tt_parts.append(f"tt1=${ctx['tt1']:.2f}")
    if ctx.get('tt2') is not None:
        tt_parts.append(f"tt2=${ctx['tt2']:.2f}")
    if ctx.get('tt3') is not None:
        tt_parts.append(f"tt3=${ctx['tt3']:.2f}")
    if tt_parts:
        parts.append(" ".join(tt_parts))
    elif ctx.get('truth_tick') is not None:
        parts.append(f"TT=${ctx['truth_tick']:.2f}")
    
    return " | ".join(parts)


def format_rev_order_log(
    symbol: str,
    rev_action: str,
    qty: float,
    rev_price: float,
    tag: str,
    rev_type: str,
    method: str,
    fill_action: str,
    fill_price: float,
    bid: Optional[float] = None,
    ask: Optional[float] = None,
    profit_save: Optional[float] = None,
    ctx: Optional[Dict[str, Any]] = None
) -> str:
    """Format a comprehensive REV order log line."""
    if ctx is None:
        ctx = get_order_context(symbol)
    
    parts = [
        f"📤 [REV_ORDER] {symbol} {rev_action} {qty} @ ${rev_price:.2f}",
        f"Tag: {tag}",
        f"Type: {rev_type}",
        f"Method: {method}",
        f"Fill: {fill_action} @ ${fill_price:.2f}",
    ]
    
    if profit_save is not None:
        parts.append(f"Profit/Save: ${profit_save:.2f}")
    
    # Bid/Ask
    b = bid if bid else ctx.get('bid')
    a = ask if ask else ctx.get('ask')
    bid_str = f"${b:.2f}" if b else "N/A"
    ask_str = f"${a:.2f}" if a else "N/A"
    parts.append(f"Bid: {bid_str} Ask: {ask_str}")
    
    # PFF
    if ctx.get('pff'):
        parts.append(f"PFF@rev: ${ctx['pff']:.2f}")
    
    # Volav
    volav_str = _format_volav(ctx)
    if volav_str:
        parts.append(volav_str)
    
    return " | ".join(parts)


def format_fronted_log(
    symbol: str,
    action: str,
    quantity: int,
    base_price: float,
    final_price: float,
    sacrifice: float,
    tag: str,
    bid: Optional[float] = None,
    ask: Optional[float] = None,
    ctx: Optional[Dict[str, Any]] = None
) -> str:
    """Format a comprehensive Frontlama log line."""
    if ctx is None:
        ctx = get_order_context(symbol)
    
    parts = [
        f"🔄 [FRONTED] {symbol} {action} {quantity}",
        f"Price: ${base_price:.2f} → ${final_price:.2f} (sacrifice: ${sacrifice:.2f})",
        f"Tag: {tag}",
    ]
    
    # Bid/Ask
    b = bid if bid else ctx.get('bid')
    a = ask if ask else ctx.get('ask')
    bid_str = f"${b:.2f}" if b else "N/A"
    ask_str = f"${a:.2f}" if a else "N/A"
    parts.append(f"Bid: {bid_str} Ask: {ask_str}")
    
    # PFF
    if ctx.get('pff'):
        parts.append(f"PFF@fronted: ${ctx['pff']:.2f}")
    
    # Metrics
    metrics = []
    if ctx.get('fbtot') is not None:
        metrics.append(f"FBtot={ctx['fbtot']:.2f}")
    if ctx.get('sfstot') is not None:
        metrics.append(f"SFStot={ctx['sfstot']:.2f}")
    if ctx.get('gort') is not None:
        metrics.append(f"GORT={ctx['gort']:.2f}")
    if metrics:
        parts.append(" ".join(metrics))
    
    # Volav
    volav_str = _format_volav(ctx)
    if volav_str:
        parts.append(volav_str)
    
    return " | ".join(parts)
