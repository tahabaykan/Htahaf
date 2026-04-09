"""
Metrics Collector — Gathers trading system state from Redis and in-memory services.

Produces a structured snapshot dict consumed by the TradingObserverAgent.
Each data source is wrapped in try/except — collector degrades gracefully
if some services are unavailable.
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional

from app.core.logger import logger


class MetricsCollector:
    """
    Collects trading metrics from all available data sources.
    
    Data Sources:
    1. Redis (most reliable) — positions, BEFDAY, dual process state, XNL state
    2. In-memory services — XNL engine state, exposure calculator, MinMax
    3. Computed — fill rate, anomalies
    """

    def collect_snapshot(self) -> Dict[str, Any]:
        """
        Collect a complete system snapshot (LEGACY — for backward compatibility).
        
        Returns:
            Dict with all available metrics, missing data = None
        """
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "system": self._collect_system_state(),
            "accounts": {},
            "xnl_engine": self._collect_xnl_state(),
            "order_flow": self._collect_order_flow(),
            "rev_orders": self._collect_rev_orders(),
            "dual_process_detail": self._collect_dual_process_detail(),
            "qebench": self._collect_qebench(),
            "todays_fills": self._collect_todays_fills(),
            "price_action": self._collect_price_action(),
            "anomalies_detected": [],
        }

        # Per-account metrics (including NEW: position_coverage + befday_health)
        account_ids = self._get_account_ids()
        for account_id in account_ids:
            acct_metrics = self._collect_account_metrics(account_id)
            acct_metrics["position_coverage"] = self._collect_position_coverage(account_id)
            acct_metrics["befday_health"] = self._collect_befday_health(account_id)
            snapshot["accounts"][account_id] = acct_metrics

        # Rule-based anomaly pre-detection (helps LLM focus)
        snapshot["anomalies_detected"] = self._detect_anomalies(snapshot)

        return snapshot

    # ═══════════════════════════════════════════════════════════════
    # QAGENTT v2 — Smart Hybrid Comprehensive Payload
    # ═══════════════════════════════════════════════════════════════

    def collect_qagentt_payload(self, include_tt_history: bool = False) -> Dict[str, Any]:
        """
        Collect FULL payload for QAGENTT v2 Smart Hybrid.
        
        Two modes:
        - include_tt_history=False (default, for Haiku SCAN): 
          Basic metrics for all tickers, NO truth tick history → fast, low tokens
        - include_tt_history=True (for Sonnet DEEP):
          Adds truth tick history (last 15 ticks, volav, temporal) 
          for ACTIVE symbols only (positions/orders/fills)
        
        Returns compact but comprehensive data:
        - ~150 tickers with ALL metrics (~200 token each basic, ~400 with tt_hist)
        - ETF strip with daily changes
        - Positions per account
        - Open orders
        - Today's fills
        - DOS group summaries
        - Exposure status
        - Anomaly score (triggers Sonnet if high enough)
        """
        # Collect positions, orders, fills FIRST — we need them to determine "active symbols"
        positions = self._collect_all_positions()
        orders = self._collect_all_open_orders()
        fills = self._collect_todays_fills_compact()
        
        # Build "active symbols" set (only used when include_tt_history=True)
        active_symbols = set()
        if include_tt_history:
            for acct_positions in (positions or {}).values():
                for pos in (acct_positions or []):
                    sym = pos.get("s")
                    if sym:
                        active_symbols.add(sym)
            for acct_orders in (orders or {}).values():
                for order in (acct_orders or []):
                    sym = order.get("s")
                    if sym:
                        active_symbols.add(sym)
            for fill in (fills or []):
                sym = fill.get("s")
                if sym:
                    active_symbols.add(sym)
        
        payload = {
            "ts": datetime.now().strftime("%H:%M:%S"),
            "tickers": self._collect_full_ticker_scan(active_symbols=active_symbols),
            "etf": self._collect_etf_strip(),
            "positions": positions,
            "orders": orders,
            "fills": fills,
            "groups": self._collect_dos_group_summary(),
            "qebench": self._collect_qebench_summary(),
            "exposure": self._collect_exposure_status(),
            "system": self._collect_system_brief(),
            "active_symbol_count": len(active_symbols),
            "anomaly_score": 0,  # Will be computed below
        }
        
        # Compute anomaly score (0-10) — triggers Sonnet DEEP if >= 3
        payload["anomaly_score"] = self._compute_anomaly_score(payload)
        
        return payload

    def _collect_full_ticker_scan(self, active_symbols: set = None) -> List[Dict[str, Any]]:
        """
        Collect compact snapshot for ALL tracked tickers.
        
        Uses DataFabric.get_fast_snapshot() as primary source.
        Adds truth tick data from Redis.
        
        SMART FILTERING:
        - ALL ~450 tickers get basic metrics (bid/ask/gort/etc + latest truth tick)
        - Only ACTIVE symbols (positions/orders/fills) get truth tick HISTORY
          (last 15 ticks, volav state, temporal analysis)
        - This keeps token usage manageable (~200 tokens for basic, ~400 for active)
        
        Compact format per ticker:
        Basic: {s, g, b, a, l, sp, dc, bc, gort, fbt, sfs, thg, sf,
                s63, s246, uc, ph, adv, tt, tta, ttv}
        Active adds: {tt_hist, tt_span_sec, state, state_conf, tt_count, v1_shift, ta}
        """
        active_symbols = active_symbols or set()
        tickers = []
        
        try:
            from app.core.data_fabric import DataFabric
            fabric = DataFabric()
            
            if not fabric.is_ready():
                return []
            
            # Get all symbols from static data (these are our ~443 tracked tickers)
            all_symbols = fabric.get_all_static_symbols()
            if not all_symbols:
                return []
            
            # Get truth ticks in batch from Redis (latest only — for ALL symbols)
            truth_ticks = self._batch_get_truth_ticks(all_symbols)
            
            # Get truth tick inspect data ONLY for active symbols (positions/orders/fills)
            # This is the heavy data: last 100 ticks, volav, temporal analysis
            active_list = [s for s in all_symbols if s in active_symbols]
            inspect_data_batch = self._batch_get_truth_inspect(active_list) if active_list else {}
            
            for symbol in all_symbols:
                try:
                    snap = fabric.get_fast_snapshot(symbol)
                    if not snap:
                        continue
                    
                    has_live = snap.get('_has_live', False)
                    
                    bid = snap.get('bid')
                    ask = snap.get('ask')
                    last = snap.get('last')
                    
                    # Use truth tick price as fallback if no live last price
                    tt_data = truth_ticks.get(symbol)
                    if (not last or float(last or 0) <= 0) and tt_data:
                        last = tt_data.get("price")
                    
                    if not last or float(last or 0) <= 0:
                        continue  # No price at all — skip
                    
                    # Compact ticker data (static + live when available)
                    ticker = {
                        "s": symbol,
                        "g": snap.get('GROUP', ''),
                        "cg": snap.get('CGRUP', ''),
                        "b": round(float(bid), 2) if bid else None,
                        "a": round(float(ask), 2) if ask else None,
                        "l": round(float(last), 2),
                        "live": has_live,  # Tell AI if data is live or stale
                        "sp": round(float(ask) - float(bid), 3) if bid and ask else None,
                        "dc": round(float(snap.get('daily_chg', 0) or 0), 3),
                        "bc": round(float(snap.get('bench_chg', 0) or 0), 3),
                        "gort": round(float(snap.get('GORT', 0) or 0), 2),
                        "fbt": round(float(snap.get('Fbtot', 0) or 0), 2),
                        "sfs": round(float(snap.get('SFStot', 0) or 0), 2),
                        "thg": round(float(snap.get('FINAL_THG', 0) or 0), 1),
                        "sf": round(float(snap.get('SHORT_FINAL', 0) or 0), 1),
                        "s63": round(float(snap.get('SMA63chg', 0) or 0), 2),
                        "s246": round(float(snap.get('SMA246chg', 0) or 0), 2),
                        "uc": round(float(snap.get('Bid_buy_ucuzluk_skoru', 0) or 0), 3),
                        "ph": round(float(snap.get('Ask_sell_pahalilik_skoru', 0) or 0), 3),
                        "adv": int(float(snap.get('AVG_ADV', 0) or 0)),
                    }
                    
                    # Add truth tick data if available
                    tt = truth_ticks.get(symbol)
                    if tt:
                        ticker["tt"] = round(tt.get("price", 0), 2)
                        ticker["tta"] = tt.get("age_sec", 9999)
                        ticker["ttv"] = tt.get("venue", "?")
                    
                    # Add truth tick history + microstructure (from inspect data)
                    inspect = inspect_data_batch.get(symbol)
                    if inspect:
                        # Last 15 truth ticks (compact: time, price, size, venue)
                        path = inspect.get("path_dataset") or []
                        if path:
                            recent_15 = path[-15:]
                            ticker["tt_hist"] = [
                                {
                                    "t": round(t.get("timestamp", 0)),
                                    "p": round(t.get("price", 0), 2),
                                    "sz": t.get("size", 0),
                                    "v": (t.get("venue") or "?")[:4],  # Truncate venue name
                                }
                                for t in recent_15
                            ]
                            # Time span of last 15 ticks (seconds)
                            if len(recent_15) >= 2:
                                first_ts = recent_15[0].get("timestamp", 0)
                                last_ts = recent_15[-1].get("timestamp", 0)
                                ticker["tt_span_sec"] = int(last_ts - first_ts) if first_ts and last_ts else None
                        
                        # Volav state (market microstructure)
                        summary = inspect.get("summary") or {}
                        if summary:
                            ticker["state"] = summary.get("state", "?")
                            ticker["state_conf"] = round(summary.get("state_confidence", 0), 2)
                            ticker["tt_count"] = summary.get("truth_tick_count_200", 0)
                            # Volav1 displacement (price shift)
                            shift = summary.get("volav_shift")
                            if shift is not None:
                                ticker["v1_shift"] = round(float(shift), 3)
                        
                        # Temporal analysis (1h/4h/1d/2d changes in cents)
                        temporal = inspect.get("temporal_analysis") or {}
                        if temporal:
                            ta = {}
                            for tf in ("1h", "4h", "1d", "2d"):
                                tfdata = temporal.get(tf) or {}
                                chg = tfdata.get("change")
                                if chg is not None:
                                    ta[tf] = round(float(chg), 3)
                            if ta:
                                ticker["ta"] = ta  # Temporal analysis: {"1h": -0.05, "4h": 0.12, ...}
                    
                    tickers.append(ticker)
                    
                except Exception:
                    continue
            
        except Exception as e:
            logger.warning(f"[METRICS] Full ticker scan error: {e}")
        
        return tickers

    def _batch_get_truth_ticks(self, symbols: List[str]) -> Dict[str, Dict]:
        """Batch-fetch truth tick data from Redis for all symbols."""
        result = {}
        redis = self._get_redis()
        if not redis:
            return result
        
        try:
            now = datetime.now().timestamp()
            
            # Use pipeline for efficiency
            pipe = redis.pipeline() if hasattr(redis, 'pipeline') else None
            
            if pipe:
                for sym in symbols:
                    # TruthTicksEngine persists to tt:ticks:{symbol}
                    pipe.get(f"tt:ticks:{sym}")
                
                values = pipe.execute()
                
                for i, raw in enumerate(values):
                    if raw:
                        try:
                            ticks = json.loads(raw)
                            if not ticks or not isinstance(ticks, list):
                                continue
                            # Get the last (most recent) tick
                            last_tick = ticks[-1]
                            tt_ts = last_tick.get("ts", 0)
                            age_sec = int(now - tt_ts) if isinstance(tt_ts, (int, float)) else 9999
                            
                            result[symbols[i]] = {
                                "price": float(last_tick.get("price", 0)),
                                "venue": last_tick.get("exch", "?"),
                                "lot": int(last_tick.get("size", 0)),
                                "age_sec": age_sec,
                                "total_ticks": len(ticks),
                            }
                        except Exception:
                            pass
            else:
                # Fallback: individual gets (slower)
                for sym in symbols[:50]:  # Cap if no pipeline
                    raw = redis.get(f"tt:ticks:{sym}")
                    if raw:
                        try:
                            ticks = json.loads(raw)
                            if not ticks or not isinstance(ticks, list):
                                continue
                            last_tick = ticks[-1]
                            tt_ts = last_tick.get("ts", 0)
                            age_sec = int(now - tt_ts) if isinstance(tt_ts, (int, float)) else 9999
                            
                            result[sym] = {
                                "price": float(last_tick.get("price", 0)),
                                "venue": last_tick.get("exch", "?"),
                                "lot": int(last_tick.get("size", 0)),
                                "age_sec": age_sec,
                                "total_ticks": len(ticks),
                            }
                        except Exception:
                            pass
        except Exception as e:
            logger.debug(f"[METRICS] Truth tick batch error: {e}")
        
        return result

    def _batch_get_truth_inspect(self, symbols: List[str]) -> Dict[str, Dict]:
        """
        Batch-fetch truth tick inspect data from Redis.
        
        Returns per-symbol: path_dataset (last 100 ticks), summary (volav state),
        temporal_analysis (1h/4h/1d/2d changes), filtering_report.
        
        This gives the QAGENTT agent deep insight into each stock's:
        - Trading frequency (some stocks trade every minute, others every 2 hours)
        - Volume patterns (lot sizes, venue distribution)
        - Price evolution (truth tick path)
        - Market microstructure state (BUYER_DOMINANT, SELLER_VACUUM, etc.)
        """
        result = {}
        redis = self._get_redis()
        if not redis:
            return result
        
        try:
            pipe = redis.pipeline() if hasattr(redis, 'pipeline') else None
            
            if pipe:
                for sym in symbols:
                    pipe.get(f"truth_ticks:inspect:{sym}")
                
                values = pipe.execute()
                
                for i, raw in enumerate(values):
                    if raw:
                        try:
                            data = json.loads(raw)
                            # Extract the nested "data" field (inspect API wraps in {success, symbol, data})
                            inspect_inner = data.get("data") or data
                            result[symbols[i]] = inspect_inner
                        except (json.JSONDecodeError, ValueError):
                            pass
            else:
                # Fallback: individual gets (slower, cap at 50)
                for sym in symbols[:50]:
                    raw = redis.get(f"truth_ticks:inspect:{sym}")
                    if raw:
                        try:
                            data = json.loads(raw)
                            inspect_inner = data.get("data") or data
                            result[sym] = inspect_inner
                        except (json.JSONDecodeError, ValueError):
                            pass
                            
        except Exception as e:
            logger.debug(f"[METRICS] Truth inspect batch error: {e}")
        
        return result

    def _collect_etf_strip(self) -> Optional[Dict[str, Any]]:
        """
        Collect ETF data with daily changes.
        
        Critical for understanding preferred stock movements:
        - TLT ↑ → kuponlular ↓ (ters korelasyon)
        - PFF → direkt preferred sentiment
        - HYG/JNK → kredi spread'i göstergesi
        - SPY → genel risk iştahı
        - VNQ → REIT preferred'lar özellikle
        """
        try:
            from app.core.data_fabric import DataFabric
            fabric = DataFabric()
            
            etf_symbols = ["TLT", "SPY", "PFF", "HYG", "JNK", "SJNK", "VNQ", "AGG"]
            etf_data = {}
            
            for sym in etf_symbols:
                live = fabric.get_etf_live(sym)
                prev_close = fabric.get_etf_prev_close(sym)
                
                if live:
                    last = float(live.get('last', 0) or 0)
                    pc = float(prev_close) if prev_close else 0
                    daily_chg = round(last - pc, 3) if pc > 0 else 0
                    daily_pct = round((last - pc) / pc * 100, 2) if pc > 0 else 0
                    
                    etf_data[sym] = {
                        "l": round(last, 2),
                        "dc": daily_chg,
                        "dp": daily_pct,
                    }
            
            return etf_data if etf_data else None
            
        except Exception as e:
            logger.debug(f"[METRICS] ETF strip error: {e}")
            return None

    def _collect_all_positions(self) -> Optional[Dict[str, List]]:
        """Collect positions for ALL accounts in compact format."""
        redis = self._get_redis()
        if not redis:
            return None
        
        result = {}
        for account_id in self._get_account_ids():
            try:
                key = f"psfalgo:positions:{account_id}"
                raw = redis.get(key)
                if not raw:
                    continue
                
                positions = json.loads(raw)
                if isinstance(positions, dict):
                    pos_list = [v for k, v in positions.items() if k != '_meta']
                elif isinstance(positions, list):
                    pos_list = positions
                else:
                    continue
                
                compact_positions = []
                for pos in pos_list:
                    sym = pos.get("symbol", pos.get("Symbol", ""))
                    qty = float(pos.get("quantity", pos.get("qty", pos.get("Quantity", 0))))
                    avg = float(pos.get("avg_price", pos.get("avgPrice", pos.get("price", 0))))
                    
                    if sym and qty != 0:
                        compact_positions.append({
                            "s": sym,
                            "q": int(qty),
                            "avg": round(avg, 2),
                            "val": round(abs(qty * avg), 0),
                            "side": "L" if qty > 0 else "S",
                        })
                
                if compact_positions:
                    # Sort by absolute value (biggest positions first)
                    compact_positions.sort(key=lambda x: x["val"], reverse=True)
                    result[account_id] = compact_positions
                    
            except Exception as e:
                logger.debug(f"[METRICS] Position collection error for {account_id}: {e}")
        
        return result if result else None

    def _collect_all_open_orders(self) -> Optional[Dict[str, List]]:
        """Collect open orders for all accounts in compact format."""
        result = {}
        
        # Hammer Pro orders
        try:
            from app.trading.hammer_orders_service import get_hammer_orders_service
            svc = get_hammer_orders_service()
            if svc:
                orders = svc.get_orders()
                compact = []
                for o in orders:
                    compact.append({
                        "s": o.get("symbol", ""),
                        "act": o.get("action", ""),
                        "q": o.get("qty", 0),
                        "p": round(float(o.get("price", 0)), 2),
                        "tag": o.get("tag", o.get("engine", "")),
                    })
                if compact:
                    result["HAMPRO"] = compact
        except Exception as e:
            logger.debug(f"[METRICS] Hammer orders error: {e}")
        
        # IBKR orders would need connector — skip for now
        
        return result if result else None

    def _collect_todays_fills_compact(self) -> Optional[Dict[str, Any]]:
        """Collect today's fills in compact format with summary."""
        try:
            from app.trading.daily_fills_store import get_daily_fills_store
            store = get_daily_fills_store()
            
            result = {}
            for account_type in ["HAMMER_PRO", "IBKR_PED", "IBKR_GUN"]:
                fills = store.get_all_fills(account_type)
                if not fills:
                    continue
                
                buys = [f for f in fills if f.get("action", "").upper() == "BUY"]
                sells = [f for f in fills if f.get("action", "").upper() in ["SELL", "SHORT"]]
                
                # Last 10 fills for detail
                recent = []
                for f in fills[:10]:
                    recent.append({
                        "s": f.get("symbol"),
                        "act": f.get("action"),
                        "q": f.get("qty"),
                        "p": f.get("price"),
                        "t": f.get("time"),
                        "tag": f.get("tag"),
                        "bc": f.get("bench_chg"),
                    })
                
                result[account_type] = {
                    "cnt": len(fills),
                    "buy": len(buys),
                    "sell": len(sells),
                    "vol": round(sum(f.get("qty", 0) * f.get("price", 0) for f in fills), 0),
                    "syms": len(set(f.get("symbol", "") for f in fills)),
                    "recent": recent,
                }
            
            return result if result else None
            
        except Exception as e:
            logger.debug(f"[METRICS] Fill compact error: {e}")
            return None

    def _collect_dos_group_summary(self) -> Optional[Dict[str, Any]]:
        """
        Collect DOS group-level summary.
        For each group: avg bench_chg, avg GORT, member count, best/worst member.
        """
        try:
            from app.core.data_fabric import DataFabric
            fabric = DataFabric()
            
            if not fabric.is_ready():
                return None
            
            groups = {}
            
            for symbol in fabric.get_all_static_symbols():
                snap = fabric.get_fast_snapshot(symbol)
                if not snap or not snap.get('_has_live'):
                    continue
                
                group = snap.get('GROUP', '')
                if not group:
                    continue
                
                if group not in groups:
                    groups[group] = {
                        "members": [],
                        "daily_chgs": [],
                        "bench_chgs": [],
                        "gorts": [],
                    }
                
                dc = float(snap.get('daily_chg', 0) or 0)
                bc = float(snap.get('bench_chg', 0) or 0)
                gort = float(snap.get('GORT', 0) or 0)
                
                groups[group]["members"].append(symbol)
                groups[group]["daily_chgs"].append(dc)
                groups[group]["bench_chgs"].append(bc)
                groups[group]["gorts"].append((symbol, gort))
            
            # Compute summaries
            result = {}
            for group, data in groups.items():
                n = len(data["members"])
                if n == 0:
                    continue
                
                avg_dc = sum(data["daily_chgs"]) / n
                gorts_sorted = sorted(data["gorts"], key=lambda x: x[1])
                
                result[group] = {
                    "n": n,
                    "avg_dc": round(avg_dc, 3),
                    "best": {"s": gorts_sorted[-1][0], "gort": round(gorts_sorted[-1][1], 2)} if gorts_sorted else None,
                    "worst": {"s": gorts_sorted[0][0], "gort": round(gorts_sorted[0][1], 2)} if gorts_sorted else None,
                }
            
            return result if result else None
            
        except Exception as e:
            logger.debug(f"[METRICS] DOS group summary error: {e}")
            return None

    def _collect_qebench_summary(self) -> Optional[Dict[str, Any]]:
        """Collect compact QeBench outperformance summary per account."""
        try:
            from app.qebench import get_qebench_csv
            
            result = {}
            for account_key in ["HAMMER_PRO", "IBKR_PED", "IBKR_GUN"]:
                try:
                    csv_mgr = get_qebench_csv(account=account_key)
                    positions = csv_mgr.get_all_positions()
                    if not positions:
                        continue
                    
                    outperform = 0
                    total = 0
                    for pos in positions:
                        avg_cost = float(pos.get("weighted_avg_cost", 0))
                        bench_fill = float(pos.get("weighted_bench_fill", 0))
                        qty = float(pos.get("total_qty", 0))
                        
                        if avg_cost <= 0 or bench_fill <= 0:
                            continue
                        total += 1
                        
                        if (avg_cost < bench_fill and qty > 0) or (avg_cost > bench_fill and qty < 0):
                            outperform += 1
                    
                    if total > 0:
                        result[account_key] = {
                            "total": total,
                            "outperform": outperform,
                            "pct": round(outperform / total * 100, 1),
                        }
                except Exception:
                    continue
            
            return result if result else None
            
        except Exception as e:
            logger.debug(f"[METRICS] QeBench summary error: {e}")
            return None

    def _collect_exposure_status(self) -> Optional[Dict[str, Any]]:
        """Collect exposure status for all accounts.
        
        Reads from psfalgo:exposure:{account_id} — written by exposure_calculator.
        Falls back to live calculation if Redis cache is empty.
        """
        redis = self._get_redis()
        result = {}
        
        for account_id in self._get_account_ids():
            try:
                # ── SOURCE 1: Redis cache ──
                if redis:
                    key = f"psfalgo:exposure:{account_id}"
                    raw = redis.get(key)
                    if raw:
                        data = json.loads(raw)
                        result[account_id] = {
                            "pct": round(float(data.get("exposure_pct", 0)), 2),
                            "pot": round(float(data.get("pot_total", 0)), 0),
                            "max": round(float(data.get("pot_max", 1400000)), 0),
                            "regime": data.get("mode", "UNKNOWN"),
                            "long_val": round(float(data.get("long_value", 0)), 0),
                            "short_val": round(float(data.get("short_value", 0)), 0),
                            "pos_count": int(data.get("position_count", 0)),
                        }
                        continue
                
                # ── SOURCE 2: Live calculation fallback ──
                try:
                    exp = self._collect_exposure(account_id)
                    if exp:
                        result[account_id] = {
                            "pct": exp.get("exposure_pct", 0),
                            "pot": round(exp.get("pot_total", 0), 0),
                            "max": round(exp.get("pot_max", 1400000), 0),
                            "regime": exp.get("mode", "UNKNOWN"),
                            "long_val": round(exp.get("long_value", 0), 0),
                            "short_val": round(exp.get("short_value", 0), 0),
                        }
                except Exception:
                    pass
                    
            except Exception:
                continue
        
        return result if result else None

    def _collect_system_brief(self) -> Dict[str, Any]:
        """Collect brief system status."""
        state = self._collect_system_state()
        dp = state.get("dual_process", {}) or {}
        
        return {
            "dp_state": dp.get("state", "UNKNOWN"),
            "current_acct": dp.get("current_account", "?"),
            "xnl_running": state.get("xnl_running", False),
            "loop": dp.get("loop_count", 0),
        }

    def _compute_anomaly_score(self, payload: Dict[str, Any]) -> int:
        """
        Compute anomaly score (0-10) from payload.
        Score >= 5 triggers Sonnet DEEP analysis.
        
        Scoring:
        - Exposure > 90%: +3
        - Exposure > 84.9%: +1
        - QeBench underperform > 60%: +2
        - ETF big move (TLT > 0.5%): +2
        - Many fills today (> 30): +1
        - DOS group avg_dc > 0.30 or < -0.30: +2
        """
        score = 0
        
        # Exposure check
        exposure = payload.get("exposure") or {}
        for acc, exp_data in exposure.items():
            pct = exp_data.get("pct", 0)
            if pct > 90:
                score += 3
            elif pct > 84.9:
                score += 1
        
        # QeBench — NOT an anomaly signal for mean reversion portfolios
        # Low outperform % is expected: we buy underperformers, sell outperformers
        # (Removed from anomaly scoring)
        
        # ETF big moves
        etf = payload.get("etf") or {}
        tlt = etf.get("TLT", {})
        if abs(tlt.get("dp", 0)) > 0.5:
            score += 2
        
        pff = etf.get("PFF", {})
        if abs(pff.get("dp", 0)) > 0.3:
            score += 1
        
        # Fill activity
        fills = payload.get("fills") or {}
        total_fills = sum(f.get("cnt", 0) for f in fills.values())
        if total_fills > 30:
            score += 1
        
        # DOS group big moves
        groups = payload.get("groups") or {}
        big_group_moves = sum(1 for g in groups.values() if abs(g.get("avg_dc", 0)) > 0.30)
        if big_group_moves >= 3:
            score += 2
        
        return min(score, 10)

    # ═══════════════════════════════════════════════════════════════
    # Redis Helper
    # ═══════════════════════════════════════════════════════════════

    def _get_redis(self):
        """Get Redis sync client."""
        try:
            from app.core.redis_client import get_redis_client
            client = get_redis_client()
            return getattr(client, "sync", client)
        except Exception:
            return None

    # ═══════════════════════════════════════════════════════════════
    # System State (Dual Process, XNL)
    # ═══════════════════════════════════════════════════════════════

    def _collect_system_state(self) -> Dict[str, Any]:
        """Collect dual process and XNL running state from Redis."""
        state = {
            "dual_process": None,
            "xnl_running": False,
            "xnl_running_account": None,
            "active_account": None,
        }

        redis = self._get_redis()
        if not redis:
            return state

        try:
            # Dual process state
            dp_raw = redis.get("psfalgo:dual_process:state")
            if dp_raw:
                dp = json.loads(dp_raw)
                state["dual_process"] = {
                    "state": dp.get("state"),
                    "accounts": dp.get("accounts", []),
                    "current_account": dp.get("current_account"),
                    "loop_count": dp.get("loop_count", 0),
                    "started_at": dp.get("started_at"),
                }

            # XNL running status
            xnl_running = redis.get("psfalgo:xnl:running")
            state["xnl_running"] = xnl_running == "1"

            # Active account
            state["xnl_running_account"] = redis.get("psfalgo:xnl:running_account")
            state["active_account"] = redis.get("psfalgo:trading:account_mode")

        except Exception as e:
            logger.warning(f"[METRICS] System state collection error: {e}")

        return state

    def _get_account_ids(self) -> List[str]:
        """Get account IDs from dual process state."""
        redis = self._get_redis()
        if not redis:
            return []

        try:
            dp_raw = redis.get("psfalgo:dual_process:state")
            if dp_raw:
                dp = json.loads(dp_raw)
                return dp.get("accounts", [])
            
            # Fallback: check active account
            active = redis.get("psfalgo:trading:account_mode")
            return [active] if active else []
        except Exception:
            return []

    # ═══════════════════════════════════════════════════════════════
    # XNL Engine State (in-memory)
    # ═══════════════════════════════════════════════════════════════

    def _collect_xnl_state(self) -> Optional[Dict[str, Any]]:
        """Collect XNL engine state from in-memory service."""
        try:
            from app.xnl.xnl_engine import get_xnl_engine
            engine = get_xnl_engine()
            if not engine:
                return None

            return {
                "state": engine.state.state.value if hasattr(engine.state.state, 'value') else str(engine.state.state),
                "total_orders_sent": engine.state.total_orders_sent,
                "total_orders_cancelled": engine.state.total_orders_cancelled,
                "total_front_cycles": engine.state.total_front_cycles,
                "total_refresh_cycles": engine.state.total_refresh_cycles,
                "started_at": engine.state.started_at.isoformat() if engine.state.started_at else None,
                "last_error": engine.state.last_error,
            }
        except Exception as e:
            logger.debug(f"[METRICS] XNL state not available: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════
    # Per-Account Metrics (positions, exposure, MinMax)
    # ═══════════════════════════════════════════════════════════════

    def _collect_account_metrics(self, account_id: str) -> Dict[str, Any]:
        """Collect all metrics for a single account."""
        metrics = {
            "account_id": account_id,
            "positions": self._collect_positions(account_id),
            "exposure": self._collect_exposure(account_id),
            "minmax": self._collect_minmax(account_id),
            "open_orders": self._collect_open_orders(account_id),
        }
        return metrics

    def _collect_positions(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Collect position data from Redis unified positions key."""
        redis = self._get_redis()
        if not redis:
            return None

        try:
            key = f"psfalgo:positions:{account_id}"
            raw = redis.get(key)
            if not raw:
                return {"count": 0, "symbols": [], "total_value": 0}

            positions = json.loads(raw)
            if isinstance(positions, dict):
                pos_list = [v for k, v in positions.items() if k != '_meta']
            elif isinstance(positions, list):
                pos_list = positions
            else:
                return {"count": 0, "symbols": [], "total_value": 0}

            # Compute summary
            symbols = []
            total_value = 0.0
            long_count = 0
            short_count = 0

            for pos in pos_list:
                sym = pos.get("symbol", pos.get("Symbol", ""))
                qty = float(pos.get("quantity", pos.get("qty", pos.get("Quantity", 0))))
                price = float(pos.get("avg_price", pos.get("avgPrice", pos.get("price", 0))))
                value = abs(qty * price)
                total_value += value

                if qty > 0:
                    long_count += 1
                elif qty < 0:
                    short_count += 1

                if sym:
                    symbols.append(sym)

            return {
                "count": len(pos_list),
                "long_count": long_count,
                "short_count": short_count,
                "symbols": symbols[:10],  # First 10 for context (avoid huge payload)
                "symbol_count": len(symbols),
                "total_value": round(total_value, 2),
            }

        except Exception as e:
            logger.debug(f"[METRICS] Position collection error for {account_id}: {e}")
            return None

    def _collect_exposure(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Collect exposure metrics.
        
        Sources:
        1. Redis cache: psfalgo:exposure:{account_id} (written by exposure_calculator)
        2. Live calculation via calculate_exposure_for_account (async → sync bridge)
        """
        try:
            # ── SOURCE 1: Redis cache (preferred, fast) ──
            redis = self._get_redis()
            if redis:
                key = f"psfalgo:exposure:{account_id}"
                raw = redis.get(key)
                if raw:
                    data = json.loads(raw)
                    pot_total = float(data.get("pot_total", 0))
                    pot_max = float(data.get("pot_max", 1400000))
                    return {
                        "pot_total": round(pot_total, 2),
                        "pot_max": round(pot_max, 2),
                        "exposure_pct": round(data.get("exposure_pct", 0), 2) if data.get("exposure_pct") else (round(pot_total / pot_max * 100, 2) if pot_max > 0 else 0),
                        "mode": data.get("mode", "UNKNOWN"),
                        "long_value": data.get("long_value", 0),
                        "short_value": data.get("short_value", 0),
                        "position_count": data.get("position_count", 0),
                        "source": "redis_cache",
                    }

            # ── SOURCE 2: Live calculation fallback ──
            try:
                import asyncio
                from app.psfalgo.exposure_calculator import calculate_exposure_for_account
                
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're already in an async context, can't await here
                    # Return None — XNL will populate Redis on next cycle
                    return None
                else:
                    exposure = loop.run_until_complete(calculate_exposure_for_account(account_id))
                    if exposure and exposure.pot_max > 0:
                        return {
                            "pot_total": round(exposure.pot_total, 2),
                            "pot_max": round(exposure.pot_max, 2),
                            "exposure_pct": round(exposure.pot_total / exposure.pot_max * 100, 2),
                            "mode": exposure.mode,
                            "long_value": round(getattr(exposure, 'long_value', 0), 2),
                            "short_value": round(getattr(exposure, 'short_value', 0), 2),
                            "source": "live_calc",
                        }
            except Exception as e:
                logger.debug(f"[METRICS] Live exposure calc failed: {e}")

            return None

        except Exception as e:
            logger.debug(f"[METRICS] Exposure collection error for {account_id}: {e}")
            return None

    def _collect_minmax(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Collect MinMax area utilization summary."""
        try:
            from app.psfalgo.minmax_area_service import get_minmax_area_service
            svc = get_minmax_area_service()
            if not svc:
                return None

            # Per-account cache lookup
            acct_cache = svc._cache_by_account.get(account_id, {})
            if not acct_cache:
                return None

            total_symbols = len(acct_cache)
            inc_exhausted = 0  # Symbols with no remaining buy capacity
            dec_exhausted = 0  # Symbols with no remaining sell capacity

            for sym, row in acct_cache.items():
                if hasattr(row, 'inc_remaining') and row.inc_remaining <= 0:
                    inc_exhausted += 1
                if hasattr(row, 'dec_remaining') and row.dec_remaining <= 0:
                    dec_exhausted += 1

            return {
                "total_symbols": total_symbols,
                "inc_exhausted": inc_exhausted,
                "dec_exhausted": dec_exhausted,
                "inc_exhausted_pct": round(inc_exhausted / total_symbols * 100, 1) if total_symbols > 0 else 0,
                "dec_exhausted_pct": round(dec_exhausted / total_symbols * 100, 1) if total_symbols > 0 else 0,
            }

        except Exception as e:
            logger.debug(f"[METRICS] MinMax collection error for {account_id}: {e}")
            return None

    def _collect_open_orders(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Collect open order count summary with per-symbol breakdown."""
        try:
            if "HAMPRO" in account_id.upper():
                from app.trading.hammer_orders_service import get_hammer_orders_service
                svc = get_hammer_orders_service()
                if svc:
                    orders = svc.get_orders()
                    buy_count = sum(1 for o in orders if (o.get("action", "").upper() in ["BUY", "COVER"]))
                    sell_count = len(orders) - buy_count
                    
                    # Per-symbol order list (for coverage analysis)
                    symbols_with_orders = set()
                    for o in orders:
                        sym = o.get("symbol", "")
                        if sym:
                            symbols_with_orders.add(sym)
                    
                    return {
                        "total": len(orders),
                        "buy_count": buy_count,
                        "sell_count": sell_count,
                        "symbols_with_orders": sorted(list(symbols_with_orders)),
                        "unique_symbols": len(symbols_with_orders),
                    }
            # IBKR open orders would need connector access
            return None
        except Exception as e:
            logger.debug(f"[METRICS] Open orders error for {account_id}: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════
    # REV Orders — Health recovery tracking
    # ═══════════════════════════════════════════════════════════════

    def _collect_rev_orders(self) -> Optional[Dict[str, Any]]:
        """Collect active REV orders from Redis."""
        redis = self._get_redis()
        if not redis:
            return None

        try:
            rev_keys = redis.keys("psfalgo:revorders:active:*")
            if not rev_keys:
                return {"active_count": 0, "symbols": []}

            rev_details = []
            for key in rev_keys:
                raw = redis.get(key)
                if raw:
                    try:
                        data = json.loads(raw)
                        rev_details.append({
                            "symbol": data.get("symbol", ""),
                            "action": data.get("action", ""),
                            "qty": data.get("qty", 0),
                            "price": data.get("price", 0),
                        })
                    except (json.JSONDecodeError, TypeError):
                        pass

            return {
                "active_count": len(rev_details),
                "symbols": [r["symbol"] for r in rev_details],
                "details": rev_details,
            }
        except Exception as e:
            logger.debug(f"[METRICS] REV orders collection error: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════
    # Position Coverage — Which positions have NO pending orders?
    # ═══════════════════════════════════════════════════════════════

    def _collect_position_coverage(self, account_id: str) -> Optional[Dict[str, Any]]:
        """
        Compare positions vs open orders to find positions with NO pending fill.
        This answers: 'Hangi pozisyonlarımız için fill bekleyen emir yok?'
        """
        redis = self._get_redis()
        if not redis:
            return None

        try:
            # 1. Get all position symbols
            pos_key = f"psfalgo:positions:{account_id}"
            pos_raw = redis.get(pos_key)
            if not pos_raw:
                return None

            positions = json.loads(pos_raw)
            if isinstance(positions, dict):
                pos_list = [v for k, v in positions.items() if k != '_meta']
            elif isinstance(positions, list):
                pos_list = positions
            else:
                return None

            position_symbols = set()
            position_map = {}
            for pos in pos_list:
                sym = pos.get("symbol", pos.get("Symbol", ""))
                qty = float(pos.get("quantity", pos.get("qty", pos.get("Quantity", 0))))
                if sym and qty != 0:
                    position_symbols.add(sym)
                    position_map[sym] = qty

            if not position_symbols:
                return {"total_positions": 0, "covered": 0, "uncovered": 0}

            # 2. Get symbols with open orders
            symbols_with_orders = set()
            
            # Try Hammer orders for HAMPRO
            if "HAMPRO" in account_id.upper():
                try:
                    from app.trading.hammer_orders_service import get_hammer_orders_service
                    svc = get_hammer_orders_service()
                    if svc:
                        for o in svc.get_orders():
                            sym = o.get("symbol", "")
                            if sym:
                                symbols_with_orders.add(sym)
                except Exception:
                    pass

            # Also check REV orders
            rev_keys = redis.keys("psfalgo:revorders:active:*")
            for key in rev_keys:
                try:
                    raw = redis.get(key)
                    if raw:
                        data = json.loads(raw)
                        sym = data.get("symbol", "")
                        if sym:
                            symbols_with_orders.add(sym)
                except Exception:
                    pass

            # 3. Compute coverage
            covered = position_symbols & symbols_with_orders
            uncovered = position_symbols - symbols_with_orders

            # Split uncovered by long/short
            uncovered_long = [s for s in uncovered if position_map.get(s, 0) > 0]
            uncovered_short = [s for s in uncovered if position_map.get(s, 0) < 0]

            return {
                "total_positions": len(position_symbols),
                "covered": len(covered),
                "uncovered": len(uncovered),
                "coverage_pct": round(len(covered) / len(position_symbols) * 100, 1) if position_symbols else 0,
                "uncovered_long": sorted(uncovered_long)[:20],  # Cap for token efficiency
                "uncovered_short": sorted(uncovered_short)[:20],
                "uncovered_long_count": len(uncovered_long),
                "uncovered_short_count": len(uncovered_short),
            }

        except Exception as e:
            logger.debug(f"[METRICS] Position coverage error for {account_id}: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════
    # BEFDAY Health Gap — Are positions healthy?
    # ═══════════════════════════════════════════════════════════════

    def _collect_befday_health(self, account_id: str) -> Optional[Dict[str, Any]]:
        """
        Compare BEFDAY (start-of-day) vs current positions to detect health gaps.
        Health gap = BEFDAY qty - Current qty (for each symbol).
        If gap exists → REV order was (or should be) placed.
        """
        redis = self._get_redis()
        if not redis:
            return None

        try:
            # Load BEFDAY data
            befday_key = f"psfalgo:befday:positions:{account_id}"
            befday_raw = redis.get(befday_key)
            if not befday_raw:
                return {"has_befday": False, "note": "No BEFDAY data — not yet captured today"}

            befday_list = json.loads(befday_raw)
            befday_map = {}
            for entry in befday_list:
                sym = entry.get("symbol", "")
                qty = float(entry.get("qty", 0))
                if sym:
                    befday_map[sym] = qty

            # Load current positions
            pos_key = f"psfalgo:positions:{account_id}"
            pos_raw = redis.get(pos_key)
            if not pos_raw:
                return {"has_befday": True, "befday_count": len(befday_map), "current_positions": 0}

            positions = json.loads(pos_raw)
            if isinstance(positions, dict):
                pos_list = [v for k, v in positions.items() if k != '_meta']
            elif isinstance(positions, list):
                pos_list = positions
            else:
                pos_list = []

            current_map = {}
            for pos in pos_list:
                sym = pos.get("symbol", pos.get("Symbol", ""))
                qty = float(pos.get("quantity", pos.get("qty", pos.get("Quantity", 0))))
                if sym:
                    current_map[sym] = qty

            # Compute health gaps
            gaps = []
            all_symbols = set(befday_map.keys()) | set(current_map.keys())
            for sym in all_symbols:
                bef_qty = befday_map.get(sym, 0)
                cur_qty = current_map.get(sym, 0)
                gap = bef_qty - cur_qty
                if abs(gap) > 0.01:  # Non-trivial gap
                    gaps.append({
                        "symbol": sym,
                        "befday_qty": bef_qty,
                        "current_qty": cur_qty,
                        "gap": gap,
                        "direction": "UNDERFILL" if gap > 0 else "OVERFILL",
                    })

            # Sort by gap magnitude
            gaps.sort(key=lambda x: abs(x["gap"]), reverse=True)

            return {
                "has_befday": True,
                "befday_count": len(befday_map),
                "current_count": len(current_map),
                "total_gaps": len(gaps),
                "underfill_count": sum(1 for g in gaps if g["direction"] == "UNDERFILL"),
                "overfill_count": sum(1 for g in gaps if g["direction"] == "OVERFILL"),
                "top_gaps": gaps[:15],  # Top 15 largest gaps
            }

        except Exception as e:
            logger.debug(f"[METRICS] BEFDAY health error for {account_id}: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════
    # Dual Process Phase Detail
    # ═══════════════════════════════════════════════════════════════

    def _collect_dual_process_detail(self) -> Optional[Dict[str, Any]]:
        """Collect detailed dual process execution info from Redis."""
        redis = self._get_redis()
        if not redis:
            return None

        try:
            dp_raw = redis.get("psfalgo:dual_process:state")
            if not dp_raw:
                return None

            dp = json.loads(dp_raw)

            # Collect timing info
            result = {
                "state": dp.get("state"),
                "current_account": dp.get("current_account"),
                "current_phase": dp.get("current_phase"),
                "loop_count": dp.get("loop_count", 0),
                "started_at": dp.get("started_at"),
                "last_switch_at": dp.get("last_switch_at"),
                "accounts": dp.get("accounts", []),
                "errors": dp.get("errors", []),
                "last_rev_count": dp.get("last_rev_count", 0),
                "total_rev_sent": dp.get("total_rev_sent", 0),
            }

            return result

        except Exception as e:
            logger.debug(f"[METRICS] Dual process detail error: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════
    # Order Flow (from XNL engine cumulative counters)
    # ═══════════════════════════════════════════════════════════════

    def _collect_order_flow(self) -> Optional[Dict[str, Any]]:
        """Collect order flow stats from XNL engine."""
        try:
            from app.xnl.xnl_engine import get_xnl_engine
            engine = get_xnl_engine()
            if not engine:
                return None

            sent = engine.state.total_orders_sent
            cancelled = engine.state.total_orders_cancelled
            net_active = max(sent - cancelled, 0)

            return {
                "total_sent": sent,
                "total_cancelled": cancelled,
                "net_active_estimate": net_active,
                "cancel_rate_pct": round(cancelled / sent * 100, 1) if sent > 0 else 0,
            }
        except Exception as e:
            logger.debug(f"[METRICS] Order flow error: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════
    # QeBench — Benchmark vs Portfolio Performance
    # ═══════════════════════════════════════════════════════════════

    def _collect_qebench(self) -> Optional[Dict[str, Any]]:
        """
        Collect QeBench outperformance data for all accounts.
        Shows how each position is performing vs its DOS Group benchmark.
        """
        try:
            from app.qebench import get_qebench_csv
            from app.qebench.benchmark import get_benchmark_fetcher
            
            bench_fetcher = get_benchmark_fetcher()
            result = {}
            
            for account_key in ["HAMMER_PRO", "IBKR_PED", "IBKR_GUN"]:
                try:
                    csv_mgr = get_qebench_csv(account=account_key)
                    positions = csv_mgr.get_all_positions()
                    
                    if not positions:
                        continue
                    
                    account_data = {
                        "position_count": len(positions),
                        "outperformers": [],
                        "underperformers": [],
                        "total_outperform_cents": 0.0,
                    }
                    
                    for pos in positions:
                        symbol = pos.get("symbol", "")
                        avg_cost = float(pos.get("weighted_avg_cost", 0))
                        bench_fill = float(pos.get("weighted_bench_fill", 0))
                        qty = float(pos.get("total_qty", 0))
                        
                        if avg_cost <= 0 or bench_fill <= 0:
                            continue
                        
                        # Get current benchmark price
                        bench_now = bench_fetcher.get_current_benchmark_price(symbol)
                        if bench_now is None:
                            continue
                        
                        # Get current price (approx from bench_now or use avg_cost as proxy)
                        # Outperform = how much better/worse than group
                        stock_move = avg_cost - bench_fill  # stock's cost vs bench at entry
                        # Positive = we bought cheaper than group avg
                        
                        entry = {
                            "symbol": symbol,
                            "qty": qty,
                            "avg_cost": round(avg_cost, 2),
                            "bench_at_fill": round(bench_fill, 2),
                            "bench_now": round(bench_now, 2),
                            "cost_vs_bench": round(avg_cost - bench_fill, 4),
                        }
                        
                        if avg_cost < bench_fill and qty > 0:
                            # Long bought below group avg = good
                            account_data["outperformers"].append(entry)
                        elif avg_cost > bench_fill and qty < 0:
                            # Short sold above group avg = good
                            account_data["outperformers"].append(entry)
                        else:
                            account_data["underperformers"].append(entry)
                    
                    # Sort by magnitude
                    account_data["outperformers"].sort(key=lambda x: abs(x["cost_vs_bench"]), reverse=True)
                    account_data["underperformers"].sort(key=lambda x: abs(x["cost_vs_bench"]), reverse=True)
                    
                    # Cap for token efficiency
                    account_data["outperformers"] = account_data["outperformers"][:10]
                    account_data["underperformers"] = account_data["underperformers"][:10]
                    account_data["outperform_count"] = len([p for p in positions if float(p.get("weighted_avg_cost", 0)) < float(p.get("weighted_bench_fill", 0))])
                    account_data["underperform_count"] = len(positions) - account_data["outperform_count"]
                    
                    result[account_key] = account_data
                    
                except Exception as e:
                    logger.debug(f"[METRICS] QeBench error for {account_key}: {e}")
                    continue
            
            return result if result else None
            
        except Exception as e:
            logger.debug(f"[METRICS] QeBench collection error: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════
    # Today's Fills — What was traded today?
    # ═══════════════════════════════════════════════════════════════

    def _collect_todays_fills(self) -> Optional[Dict[str, Any]]:
        """Collect today's fill summary from DailyFillsStore."""
        try:
            from app.trading.daily_fills_store import get_daily_fills_store
            store = get_daily_fills_store()
            
            result = {}
            for account_type in ["HAMMER_PRO", "IBKR_PED", "IBKR_GUN"]:
                fills = store.get_all_fills(account_type)
                if not fills:
                    continue
                
                buy_fills = [f for f in fills if f.get("action", "").upper() == "BUY"]
                sell_fills = [f for f in fills if f.get("action", "").upper() in ["SELL", "SHORT"]]
                
                result[account_type] = {
                    "total_fills": len(fills),
                    "buy_count": len(buy_fills),
                    "sell_count": len(sell_fills),
                    "total_value": round(sum(f.get("qty", 0) * f.get("price", 0) for f in fills), 2),
                    "unique_symbols": len(set(f.get("symbol", "") for f in fills)),
                    "last_5_fills": [
                        {
                            "symbol": f.get("symbol"),
                            "action": f.get("action"),
                            "qty": f.get("qty"),
                            "price": f.get("price"),
                            "time": f.get("time"),
                            "strategy": f.get("tag"),
                            "bench_chg": f.get("bench_chg"),
                        }
                        for f in fills[:5]  # Already sorted newest first
                    ],
                }
            
            return result if result else None
            
        except Exception as e:
            logger.debug(f"[METRICS] Fill collection error: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════
    # Price Action — Real-time market data for key symbols
    # ═══════════════════════════════════════════════════════════════

    def _collect_price_action(self) -> Optional[Dict[str, Any]]:
        """
        Collect real-time price data from DataFabric for top positions.
        Shows bid/ask/last/daily_chg for the agent to understand market context.
        """
        try:
            from app.core.data_fabric import get_data_fabric
            fabric = get_data_fabric()
            if not fabric:
                return None
            
            # Get snapshot of all symbols with recent data
            all_symbols = fabric.get_all_symbols() if hasattr(fabric, 'get_all_symbols') else []
            if not all_symbols:
                return None
            
            # Pick top movers (biggest daily change)
            movers = []
            for symbol in all_symbols[:200]:  # Cap to avoid slowdown
                try:
                    snapshot = fabric.get_snapshot(symbol)
                    derived = fabric.get_derived(symbol)
                    
                    if not snapshot:
                        continue
                    
                    last = snapshot.get('last', 0)
                    bid = snapshot.get('bid', 0)
                    ask = snapshot.get('ask', 0)
                    daily_chg = 0
                    
                    if derived:
                        daily_chg = derived.get('daily_chg', 0) or 0
                    
                    if last and float(last) > 0:
                        movers.append({
                            "symbol": symbol,
                            "last": round(float(last), 2),
                            "bid": round(float(bid), 2) if bid else None,
                            "ask": round(float(ask), 2) if ask else None,
                            "daily_chg": round(float(daily_chg), 4),
                            "spread": round(float(ask) - float(bid), 3) if bid and ask else None,
                        })
                except Exception:
                    continue
            
            if not movers:
                return None
            
            # Sort by absolute daily change
            movers.sort(key=lambda x: abs(x.get("daily_chg", 0)), reverse=True)
            
            top_gainers = [m for m in movers if m["daily_chg"] > 0][:5]
            top_losers = [m for m in movers if m["daily_chg"] < 0][:5]
            
            return {
                "total_symbols_tracked": len(movers),
                "avg_daily_chg": round(sum(m["daily_chg"] for m in movers) / len(movers), 4) if movers else 0,
                "top_gainers": top_gainers,
                "top_losers": top_losers,
            }
            
        except Exception as e:
            logger.debug(f"[METRICS] Price action collection error: {e}")
            return None

    # ═══════════════════════════════════════════════════════════════
    # Rule-Based Anomaly Detection
    # ═══════════════════════════════════════════════════════════════

    def _detect_anomalies(self, snapshot: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Pre-detect anomalies using fixed rules.
        This helps the LLM focus on important issues.
        """
        anomalies = []

        # Anomaly 1: High exposure
        for acc_id, acc_data in snapshot.get("accounts", {}).items():
            exp = acc_data.get("exposure")
            if exp and exp.get("exposure_pct", 0) > 84.9:
                level = "KRİTİK" if exp["exposure_pct"] > 92 else "UYARI"
                anomalies.append({
                    "type": "HIGH_EXPOSURE",
                    "account": acc_id,
                    "value": exp["exposure_pct"],
                    "threshold": 84.9,
                    "level": level,
                })

        # Anomaly 2: High cancel rate
        order_flow = snapshot.get("order_flow")
        if order_flow and order_flow.get("cancel_rate_pct", 0) > 80:
            anomalies.append({
                "type": "HIGH_CANCEL_RATE",
                "value": order_flow["cancel_rate_pct"],
                "threshold": 80,
                "level": "DİKKAT",
            })

        # Anomaly 3: No orders sent but XNL is running
        xnl_state = snapshot.get("xnl_engine")
        if xnl_state and xnl_state.get("state") == "RUNNING":
            if xnl_state.get("total_orders_sent", 0) == 0:
                anomalies.append({
                    "type": "XNL_RUNNING_NO_ORDERS",
                    "level": "DİKKAT",
                })

        # Anomaly 4: MinMax exhaustion over 50%
        for acc_id, acc_data in snapshot.get("accounts", {}).items():
            mm = acc_data.get("minmax")
            if mm and mm.get("inc_exhausted_pct", 0) > 50:
                anomalies.append({
                    "type": "MINMAX_INC_EXHAUSTION",
                    "account": acc_id,
                    "value": mm["inc_exhausted_pct"],
                    "threshold": 50,
                    "level": "DİKKAT",
                })

        # Anomaly 5: Dual process not running
        sys_state = snapshot.get("system", {})
        dp = sys_state.get("dual_process")
        if dp and dp.get("state") != "RUNNING":
            anomalies.append({
                "type": "DUAL_PROCESS_NOT_RUNNING",
                "state": dp.get("state"),
                "level": "UYARI",
            })

        # Anomaly 6: Low position coverage (many positions with no orders)
        for acc_id, acc_data in snapshot.get("accounts", {}).items():
            cov = acc_data.get("position_coverage")
            if cov and cov.get("coverage_pct", 100) < 30:
                anomalies.append({
                    "type": "LOW_ORDER_COVERAGE",
                    "account": acc_id,
                    "value": cov["coverage_pct"],
                    "uncovered_count": cov.get("uncovered", 0),
                    "level": "DİKKAT",
                })

        # Anomaly 7: High BEFDAY health gaps
        for acc_id, acc_data in snapshot.get("accounts", {}).items():
            bh = acc_data.get("befday_health")
            if bh and bh.get("total_gaps", 0) > 10:
                anomalies.append({
                    "type": "HIGH_HEALTH_GAPS",
                    "account": acc_id,
                    "value": bh["total_gaps"],
                    "underfills": bh.get("underfill_count", 0),
                    "overfills": bh.get("overfill_count", 0),
                    "level": "UYARI",
                })

        # Anomaly 8: Active REV orders > 5 (many unresolved health gaps)
        rev = snapshot.get("rev_orders")
        if rev and rev.get("active_count", 0) > 5:
            anomalies.append({
                "type": "MANY_ACTIVE_REV_ORDERS",
                "count": rev["active_count"],
                "symbols": rev.get("symbols", []),
                "level": "DİKKAT",
            })

        # Anomaly 9: QeBench — Many positions underperforming benchmark
        qebench = snapshot.get("qebench")
        if qebench:
            for acc_key, qb_data in qebench.items():
                underperform = qb_data.get("underperform_count", 0)
                total = qb_data.get("position_count", 0)
                if total > 5 and underperform > total * 0.7:
                    anomalies.append({
                        "type": "QEBENCH_HIGH_UNDERPERFORM",
                        "account": acc_key,
                        "underperform_count": underperform,
                        "total_positions": total,
                        "level": "UYARI",
                    })

        return anomalies

