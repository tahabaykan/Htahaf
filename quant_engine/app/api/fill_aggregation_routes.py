"""
Fill Aggregation API Routes
============================
Provides aggregated fill data grouped by account + symbol.
Separates BUY and SELL fills with weighted average prices,
weighted average fill times, and benchmark comparisons.

Example output per symbol:
  MS PRA (HAMPRO):
    BUY:  600 lots, avg_fill $20.50, avg_time 13:22, bench_price $20.45
    SELL: 400 lots, avg_fill $20.62, avg_time 14:05, bench_price $20.58
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
import csv
import os

from app.core.logger import logger

router = APIRouter(prefix="/api/fill-agg", tags=["Fill Aggregation"])

LOG_DIR = r"data/logs/daily_fills"

# ─────────────────────────────────────────────────────────
# Account mapping
# ─────────────────────────────────────────────────────────
ACCOUNT_FILE_PREFIX = {
    "HAMMER_PRO": "ham",
    "HAMPRO": "ham",
    "IBKR_PED": "ibped",
    "IBKR_GUN": "ibgun",
}


def _get_csv_path(account: str, date_str: str = None) -> str:
    """Get CSV file path for account and date."""
    prefix = ACCOUNT_FILE_PREFIX.get(account, account.lower().replace("_", ""))
    if date_str is None:
        date_str = datetime.now().strftime("%y%m%d")
    filename = f"{prefix}filledorders{date_str}.csv"
    return os.path.join(LOG_DIR, filename)


def _parse_time_to_seconds(time_str: str) -> Optional[float]:
    """Parse HH:MM:SS to seconds since midnight."""
    if not time_str:
        return None
    try:
        parts = time_str.strip().split(":")
        if len(parts) >= 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 3600 + int(parts[1]) * 60
    except (ValueError, IndexError):
        pass
    return None


def _seconds_to_time_str(seconds: float) -> str:
    """Convert seconds since midnight to HH:MM:SS."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _read_fills_from_csv(csv_path: str) -> List[Dict[str, Any]]:
    """Read all fills from a CSV file."""
    fills = []
    if not os.path.isfile(csv_path):
        return fills
    try:
        with open(csv_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    qty = float(row.get("Quantity", 0))
                    price = float(row.get("Price", 0))
                    if qty <= 0 or price <= 0:
                        continue
                    fills.append({
                        "time": row.get("Time", ""),
                        "symbol": row.get("Symbol", ""),
                        "action": (row.get("Action", "") or "").upper(),
                        "qty": qty,
                        "price": price,
                        "bid": _safe_float(row.get("Bid")),
                        "ask": _safe_float(row.get("Ask")),
                        "spread": _safe_float(row.get("Spread")),
                        "strategy": row.get("Strategy", "UNKNOWN"),
                        "bench_chg": _safe_float(row.get("Bench_Chg")),
                        "bench_source": row.get("Bench_Source", ""),
                        "bench_price": _safe_float(row.get("Bench_Price")),
                        "fill_id": row.get("FillID", ""),
                    })
                except (ValueError, TypeError):
                    continue
    except Exception as e:
        logger.error(f"[FillAgg] Error reading {csv_path}: {e}")
    return fills


def _safe_float(val) -> Optional[float]:
    """Safely convert to float, return None on failure."""
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _aggregate_fills(fills: List[Dict], account: str) -> Dict[str, Any]:
    """
    Aggregate fills by symbol, separating BUY and SELL.
    
    Returns dict keyed by symbol with buy_side and sell_side aggregations.
    Each side contains:
      - total_qty: Total lots
      - avg_fill_price: Weighted average fill price
      - avg_fill_time: Weighted average fill time
      - fill_count: Number of individual fills
      - avg_bench_price: Weighted average benchmark price at fill time
      - total_value: Total dollar value (qty × price)
      - fills: List of individual fills (for drill-down)
    """
    # Group by symbol
    symbols: Dict[str, Dict[str, list]] = defaultdict(lambda: {"BUY": [], "SELL": []})
    
    for fill in fills:
        sym = fill["symbol"]
        action = fill["action"]
        if action in ("BUY", "BUY_TO_COVER", "COVER"):
            symbols[sym]["BUY"].append(fill)
        elif action in ("SELL", "SELL_SHORT", "SHORT"):
            symbols[sym]["SELL"].append(fill)
    
    result = {}
    for sym in sorted(symbols.keys()):
        sides = symbols[sym]
        sym_data = {"symbol": sym, "account": account}
        
        for side_name in ("BUY", "SELL"):
            side_fills = sides[side_name]
            if not side_fills:
                sym_data[f"{side_name.lower()}_side"] = None
                continue
            
            total_qty = sum(f["qty"] for f in side_fills)
            total_value = sum(f["qty"] * f["price"] for f in side_fills)
            
            # Weighted average fill price
            avg_price = round(total_value / total_qty, 2) if total_qty > 0 else 0
            
            # Weighted average fill time
            time_weights = []
            for f in side_fills:
                secs = _parse_time_to_seconds(f["time"])
                if secs is not None:
                    time_weights.append((secs, f["qty"]))
            
            avg_time_str = ""
            if time_weights:
                total_tw = sum(w for _, w in time_weights)
                if total_tw > 0:
                    avg_secs = sum(s * w for s, w in time_weights) / total_tw
                    avg_time_str = _seconds_to_time_str(avg_secs)
            
            # Weighted average benchmark price
            bench_weights = []
            for f in side_fills:
                bp = f.get("bench_price")
                if bp is not None and bp > 0:
                    bench_weights.append((bp, f["qty"]))
            
            avg_bench_price = None
            if bench_weights:
                total_bw = sum(w for _, w in bench_weights)
                if total_bw > 0:
                    avg_bench_price = round(
                        sum(p * w for p, w in bench_weights) / total_bw, 2
                    )
            
            # Weighted average bid/ask at fill
            bid_weights = [(f["bid"], f["qty"]) for f in side_fills if f.get("bid")]
            ask_weights = [(f["ask"], f["qty"]) for f in side_fills if f.get("ask")]
            
            avg_bid = None
            if bid_weights:
                tw = sum(w for _, w in bid_weights)
                if tw > 0:
                    avg_bid = round(sum(p * w for p, w in bid_weights) / tw, 2)
            
            avg_ask = None
            if ask_weights:
                tw = sum(w for _, w in ask_weights)
                if tw > 0:
                    avg_ask = round(sum(p * w for p, w in ask_weights) / tw, 2)
            
            # Execution quality — how close to bid (BUY) or ask (SELL)
            exec_quality = None
            if avg_bid is not None and avg_ask is not None and avg_ask > avg_bid:
                spread = avg_ask - avg_bid
                if side_name == "BUY":
                    # BUY: lower is better. 100% = bought at bid, 0% = bought at ask
                    exec_quality = round(max(0, min(100, (avg_ask - avg_price) / spread * 100)), 1)
                else:
                    # SELL: higher is better. 100% = sold at ask, 0% = sold at bid
                    exec_quality = round(max(0, min(100, (avg_price - avg_bid) / spread * 100)), 1)
            
            # Bench comparison — cents above/below average benchmark
            bench_edge = None
            if avg_bench_price is not None:
                if side_name == "BUY":
                    # BUY: cheaper than bench = good (negative = better)
                    bench_edge = round(avg_price - avg_bench_price, 2)
                else:
                    # SELL: more expensive than bench = good (positive = better)
                    bench_edge = round(avg_price - avg_bench_price, 2)
            
            # Strategy breakdown
            strategy_counts = defaultdict(lambda: {"qty": 0, "value": 0})
            for f in side_fills:
                strat = f.get("strategy", "UNKNOWN")
                strategy_counts[strat]["qty"] += f["qty"]
                strategy_counts[strat]["value"] += f["qty"] * f["price"]
            
            sym_data[f"{side_name.lower()}_side"] = {
                "total_qty": int(total_qty),
                "avg_fill_price": round(avg_price, 2),
                "avg_fill_time": avg_time_str,
                "fill_count": len(side_fills),
                "total_value": round(total_value, 2),
                "avg_pff_at_fill": avg_bench_price,
                "bench_edge_cents": bench_edge,
                "avg_bid_at_fill": avg_bid,
                "avg_ask_at_fill": avg_ask,
                "exec_quality_pct": exec_quality,
                "strategies": {k: {"qty": int(v["qty"]), "avg_price": round(v["value"]/v["qty"], 2) if v["qty"] > 0 else 0} for k, v in strategy_counts.items()},
                "fills": [
                    {
                        "time": f["time"],
                        "qty": int(f["qty"]),
                        "price": f["price"],
                        "bid": f.get("bid"),
                        "ask": f.get("ask"),
                        "pff_price": f.get("bench_price"),
                        "strategy": f.get("strategy"),
                    }
                    for f in side_fills
                ],
            }
        
        # Net position impact
        buy_qty = sym_data.get("buy_side", {})
        sell_qty = sym_data.get("sell_side", {})
        buy_total = buy_qty["total_qty"] if isinstance(buy_qty, dict) and buy_qty else 0
        sell_total = sell_qty["total_qty"] if isinstance(sell_qty, dict) and sell_qty else 0
        sym_data["net_qty"] = buy_total - sell_total
        sym_data["net_direction"] = "LONG" if sym_data["net_qty"] > 0 else "SHORT" if sym_data["net_qty"] < 0 else "FLAT"
        
        # ─── PFF Outperformance Calculation ───
        # Compare stock profit vs PFF movement between fill times
        pff_analysis = _calculate_pff_outperformance(sym_data)
        if pff_analysis:
            sym_data["pff_analysis"] = pff_analysis
        
        result[sym] = sym_data
    
    return result


def _get_current_pff_price() -> Optional[float]:
    """Get PFF's current last price from market data caches."""
    try:
        from app.api.market_data_routes import get_etf_market_data, get_market_data
        etf_data = get_etf_market_data()
        if etf_data and "PFF" in etf_data:
            last = etf_data["PFF"].get('last') or etf_data["PFF"].get('price')
            if last and float(last) > 0:
                return round(float(last), 2)
        pff_data = get_market_data("PFF")
        if pff_data:
            last = pff_data.get('last') or pff_data.get('price')
            if last and float(last) > 0:
                return round(float(last), 2)
    except Exception:
        pass
    return None


def _get_current_stock_price(symbol: str) -> Optional[float]:
    """Get a stock's current last price from market data cache."""
    try:
        from app.api.market_data_routes import get_market_data
        data = get_market_data(symbol)
        if data:
            last = data.get('last') or data.get('price')
            if last and float(last) > 0:
                return round(float(last), 2)
    except Exception:
        pass
    return None


def _calculate_pff_outperformance(sym_data: Dict) -> Optional[Dict]:
    """
    Calculate stock outperformance vs PFF ETF benchmark.
    
    3 scenarios:
    
    1. CLOSED (both buy + sell exist):
       stock_profit  = avg_sell_price - avg_buy_price
       pff_move      = pff_at_sell - pff_at_buy
       outperformance = stock_profit - pff_move
       
    2. OPEN LONG (buy only, no sell):
       stock_unrealized = current_stock_price - avg_buy_price
       pff_move         = pff_now - pff_at_buy
       outperformance   = stock_unrealized - pff_move
       
    3. OPEN SHORT (sell only, no buy):
       stock_unrealized = avg_sell_price - current_stock_price
       pff_move         = pff_now - pff_at_sell
       outperformance   = stock_unrealized + pff_move
       (short profits when stock drops AND PFF drops = extra alpha)
    
    Returns dict with outperformance metrics or None.
    """
    buy_side = sym_data.get("buy_side")
    sell_side = sym_data.get("sell_side")
    symbol = sym_data.get("symbol", "")
    
    has_buy = buy_side and buy_side.get("total_qty", 0) > 0
    has_sell = sell_side and sell_side.get("total_qty", 0) > 0
    
    result = {"symbol": symbol}
    
    if has_buy and has_sell:
        # ── SCENARIO 1: CLOSED TRADE ──
        buy_price = buy_side["avg_fill_price"]
        sell_price = sell_side["avg_fill_price"]
        pff_at_buy = buy_side.get("avg_bench_price")
        pff_at_sell = sell_side.get("avg_bench_price")
        
        if pff_at_buy is None or pff_at_sell is None or pff_at_buy <= 0 or pff_at_sell <= 0:
            return None
        
        stock_profit = sell_price - buy_price  # Positive = profit
        pff_move = pff_at_sell - pff_at_buy    # PFF's movement over same period
        outperformance = stock_profit - pff_move
        
        # Percentage: relative to buy price
        outperf_pct = (outperformance / buy_price * 100) if buy_price > 0 else 0
        
        result.update({
            "status": "CLOSED",
            "stock_profit_cents": round(stock_profit, 2),
            "pff_move_cents": round(pff_move, 2),
            "outperformance_cents": round(outperformance, 2),
            "outperformance_pct": round(outperf_pct, 2),
            "pff_at_buy": round(pff_at_buy, 2),
            "pff_at_sell": round(pff_at_sell, 2),
            "verdict": "OUTPERFORM" if outperformance > 0 else "UNDERPERFORM",
        })
        
    elif has_buy and not has_sell:
        # ── SCENARIO 2: OPEN LONG ──
        buy_price = buy_side["avg_fill_price"]
        pff_at_buy = buy_side.get("avg_bench_price")
        
        if pff_at_buy is None or pff_at_buy <= 0:
            return None
        
        current_stock = _get_current_stock_price(symbol)
        pff_now = _get_current_pff_price()
        
        if not current_stock or not pff_now:
            # Can't compare without current prices (market closed or no data)
            result.update({
                "status": "OPEN_LONG",
                "pff_at_buy": pff_at_buy,
                "note": "Current prices not available — market may be closed",
            })
            return result
        
        stock_unrealized = current_stock - buy_price
        pff_move = pff_now - pff_at_buy
        outperformance = stock_unrealized - pff_move
        outperf_pct = (outperformance / buy_price * 100) if buy_price > 0 else 0
        
        result.update({
            "status": "OPEN_LONG",
            "stock_unrealized_cents": round(stock_unrealized, 2),
            "pff_move_cents": round(pff_move, 2),
            "outperformance_cents": round(outperformance, 2),
            "outperformance_pct": round(outperf_pct, 2),
            "pff_at_buy": round(pff_at_buy, 2),
            "pff_now": round(pff_now, 2),
            "current_stock_price": round(current_stock, 2),
            "verdict": "OUTPERFORM" if outperformance > 0 else "UNDERPERFORM",
        })
        
    elif has_sell and not has_buy:
        # ── SCENARIO 3: OPEN SHORT ──
        sell_price = sell_side["avg_fill_price"]
        pff_at_sell = sell_side.get("avg_bench_price")
        
        if pff_at_sell is None or pff_at_sell <= 0:
            return None
        
        current_stock = _get_current_stock_price(symbol)
        pff_now = _get_current_pff_price()
        
        if not current_stock or not pff_now:
            result.update({
                "status": "OPEN_SHORT",
                "pff_at_sell": pff_at_sell,
                "note": "Current prices not available — market may be closed",
            })
            return result
        
        stock_unrealized = sell_price - current_stock  # Short profit
        pff_move = pff_now - pff_at_sell
        # For shorts: we WANT PFF to go up while our stock goes down
        # outperformance = our_profit - what_market_did
        # If PFF went up $0.10 and we made $0.20 on short → outperformance = $0.10
        outperformance = stock_unrealized - pff_move
        outperf_pct = (outperformance / sell_price * 100) if sell_price > 0 else 0
        
        result.update({
            "status": "OPEN_SHORT",
            "stock_unrealized_cents": round(stock_unrealized, 2),
            "pff_move_cents": round(pff_move, 2),
            "outperformance_cents": round(outperformance, 2),
            "outperformance_pct": round(outperf_pct, 2),
            "pff_at_sell": round(pff_at_sell, 2),
            "pff_now": round(pff_now, 2),
            "current_stock_price": round(current_stock, 2),
            "verdict": "OUTPERFORM" if outperformance > 0 else "UNDERPERFORM",
        })
    else:
        return None
    
    return result


# ─────────────────────────────────────────────────────────
# STARTUP RECOVERY: Backfill from broker APIs
# ─────────────────────────────────────────────────────────

async def _backfill_from_hammer(account: str = "HAMMER_PRO") -> int:
    """
    Fetch today's filled orders from Hammer Pro API and backfill CSV.
    
    Hammer Pro's getTransactions returns ALL today's transactions.
    For filled orders, it includes a Fills[] array with individual
    partial fill details (FillID, QTY, Price, FillDT).
    
    Returns number of NEW fills added.
    """
    added = 0
    try:
        from app.trading.hammer_orders_service import get_hammer_orders_service
        from app.trading.daily_fills_store import get_daily_fills_store
        
        service = get_hammer_orders_service()
        if not service:
            logger.warning("[FillAgg] Hammer orders service not available")
            return 0
        
        filled = service.get_filled_orders()
        store = get_daily_fills_store()
        
        for order in filled:
            symbol = order.get("symbol", "")
            action = order.get("action", "")
            tag = order.get("tag") or "UNKNOWN"
            individual_fills = order.get("individual_fills", [])
            
            if not symbol:
                continue
            
            if individual_fills:
                # Use per-partial-fill breakdown for precision
                for pf in individual_fills:
                    pf_qty = pf.get("qty", 0)
                    pf_price = pf.get("price", 0)
                    pf_fill_id = pf.get("fill_id", "")
                    pf_fill_dt = pf.get("fill_dt", "")  # Actual fill timestamp
                    
                    if pf_qty <= 0 or pf_price <= 0:
                        continue
                    
                    store.log_fill(
                        account_type=account,
                        symbol=symbol,
                        action=action,
                        qty=pf_qty,
                        price=pf_price,
                        strategy_tag=tag,
                        fill_id=pf_fill_id,
                        fill_time=pf_fill_dt  # REAL fill time from broker
                    )
                    added += 1
            else:
                # Fallback: use order-level fill data
                qty = float(order.get("filled_qty") or order.get("qty", 0))
                price = float(order.get("filled_price") or order.get("price", 0))
                fill_id = order.get("order_id", "")
                filled_dt = order.get("filled_dt", "")  # Order-level fill timestamp
                
                if qty <= 0 or price <= 0:
                    continue
                
                store.log_fill(
                    account_type=account,
                    symbol=symbol,
                    action=action,
                    qty=qty,
                    price=price,
                    strategy_tag=tag,
                    fill_id=fill_id,
                    fill_time=filled_dt  # REAL fill time from broker
                )
                added += 1
        
        logger.info(f"[FillAgg] Hammer backfill: {len(filled)} orders → {added} individual fills logged (dedup applied)")
    except Exception as e:
        logger.error(f"[FillAgg] Hammer backfill error: {e}", exc_info=True)
    return added


async def _backfill_from_ibkr(account: str = "IBKR_PED") -> int:
    """
    Request today's executions from IBKR TWS/Gateway.
    
    IBKR TWS API supports reqExecutions() which returns TODAY's fills
    even after reconnect. On Gateway it returns current day only.
    On full TWS with Trade Log open, up to 7 days.
    
    Our IBNativeConnector already calls reqExecutions(1, None) on connect,
    which populates self.filled_orders via execDetails callback.
    
    Returns number of fills backfilled.
    """
    added = 0
    try:
        from app.trading.daily_fills_store import get_daily_fills_store
        store = get_daily_fills_store()
        
        # Try to get fills from IBKR connector
        try:
            from app.psfalgo.dual_connection_manager import get_dual_connection_manager
            dcm = get_dual_connection_manager()
            if dcm and hasattr(dcm, 'ibkr_connector') and dcm.ibkr_connector:
                connector = dcm.ibkr_connector
                if hasattr(connector, 'filled_orders') and connector.filled_orders:
                    for fill in connector.filled_orders:
                        symbol = fill.get("symbol", "")
                        action_raw = fill.get("action", "")
                        # IBKR uses BOT/SLD
                        if action_raw == "BOT":
                            action = "BUY"
                        elif action_raw == "SLD":
                            action = "SELL"
                        else:
                            action = action_raw.upper()
                        
                        qty = float(fill.get("qty", 0))
                        price = float(fill.get("price", 0))
                        exec_id = fill.get("exec_id", "")
                        fill_time_raw = fill.get("time", "")  # execution.time from IBKR
                        
                        if qty <= 0 or price <= 0 or not symbol:
                            continue
                        
                        store.log_fill(
                            account_type=account,
                            symbol=symbol,
                            action=action,
                            qty=qty,
                            price=price,
                            strategy_tag="UNKNOWN",
                            fill_id=exec_id,
                            fill_time=fill_time_raw  # REAL fill time from IBKR
                        )
                        added += 1
                    
                    logger.info(f"[FillAgg] IBKR backfill: {added} fills from connector (dedup applied)")
                else:
                    logger.info("[FillAgg] IBKR connector has no filled_orders yet")
            else:
                logger.info("[FillAgg] IBKR connector not available")
        except Exception as e:
            logger.debug(f"[FillAgg] IBKR connector access error: {e}")
        
        # Also check existing CSV
        if added == 0:
            csv_path = _get_csv_path(account)
            if os.path.isfile(csv_path):
                fills = _read_fills_from_csv(csv_path)
                added = len(fills)
                logger.info(f"[FillAgg] IBKR {account}: {added} fills already in today's CSV")
    except Exception as e:
        logger.error(f"[FillAgg] IBKR backfill error: {e}", exc_info=True)
    return added


# ─────────────────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────────────────

@router.get("/today")
async def get_aggregated_fills():
    """
    Get aggregated fill report for today across all accounts.
    
    Groups fills by account + symbol, separates BUY/SELL with:
    - Weighted avg fill price
    - Weighted avg fill time (lot-weighted)
    - Weighted avg benchmark price at fill time
    - Execution quality score
    - Bench edge (cents above/below group average)
    - Strategy breakdown
    """
    try:
        accounts = ["HAMMER_PRO", "IBKR_PED"]
        result = {}
        grand_summary = {
            "total_symbols": 0,
            "total_buy_value": 0,
            "total_sell_value": 0,
            "total_buy_qty": 0,
            "total_sell_qty": 0,
            "avg_exec_quality": None,
        }
        
        all_qualities = []
        
        for acct in accounts:
            csv_path = _get_csv_path(acct)
            fills = _read_fills_from_csv(csv_path)
            agg = _aggregate_fills(fills, acct)
            
            acct_summary = {
                "symbols": len(agg),
                "total_fills": sum(
                    (s.get("buy_side", {}) or {}).get("fill_count", 0) +
                    (s.get("sell_side", {}) or {}).get("fill_count", 0)
                    for s in agg.values()
                ),
            }
            
            # Collect quality scores
            for sym_data in agg.values():
                for side in ("buy_side", "sell_side"):
                    sd = sym_data.get(side)
                    if sd and sd.get("exec_quality_pct") is not None:
                        all_qualities.append(sd["exec_quality_pct"])
                    if sd:
                        if side == "buy_side":
                            grand_summary["total_buy_value"] += sd["total_value"]
                            grand_summary["total_buy_qty"] += sd["total_qty"]
                        else:
                            grand_summary["total_sell_value"] += sd["total_value"]
                            grand_summary["total_sell_qty"] += sd["total_qty"]
            
            grand_summary["total_symbols"] += len(agg)
            
            result[acct] = {
                "summary": acct_summary,
                "symbols": agg,
            }
        
        if all_qualities:
            grand_summary["avg_exec_quality"] = round(
                sum(all_qualities) / len(all_qualities), 1
            )
        
        grand_summary["total_buy_value"] = round(grand_summary["total_buy_value"], 2)
        grand_summary["total_sell_value"] = round(grand_summary["total_sell_value"], 2)
        grand_summary["net_value"] = round(
            grand_summary["total_buy_value"] - grand_summary["total_sell_value"], 2
        )
        
        return JSONResponse(content={
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "grand_summary": grand_summary,
            "accounts": result,
        })
    
    except Exception as e:
        logger.error(f"[FillAgg] Error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/today/{account_id}")
async def get_account_aggregated_fills(account_id: str):
    """Get aggregated fill report for a specific account."""
    try:
        csv_path = _get_csv_path(account_id)
        fills = _read_fills_from_csv(csv_path)
        agg = _aggregate_fills(fills, account_id)
        
        return JSONResponse(content={
            "success": True,
            "account": account_id,
            "timestamp": datetime.now().isoformat(),
            "symbol_count": len(agg),
            "fill_count": len(fills),
            "symbols": agg,
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/backfill")
async def trigger_backfill():
    """
    Trigger backfill from broker APIs.
    Useful when QE was offline and missed real-time fill events.
    
    Hammer Pro: getTransactions returns all today's filled orders with
                individual fill breakdown (Fills[]: FillID, QTY, Price, FillDT).
    
    IBKR TWS:   reqExecutions returns today's fills after reconnect.
                Already called automatically on connect_client().
    """
    try:
        results = {}
        
        # Hammer Pro backfill (with individual fills)
        ham_count = await _backfill_from_hammer("HAMMER_PRO")
        results["HAMMER_PRO"] = {
            "fills_processed": ham_count,
            "status": "OK" if ham_count >= 0 else "ERROR",
            "note": "Uses Fills[] array for per-partial-fill precision"
        }
        
        # IBKR backfill (from reqExecutions → filled_orders cache)
        ibkr_count = await _backfill_from_ibkr("IBKR_PED")
        results["IBKR_PED"] = {
            "fills_processed": ibkr_count,
            "status": "OK",
            "note": "reqExecutions returns today's fills after reconnect"
        }
        
        return JSONResponse(content={
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "results": results,
        })
    except Exception as e:
        logger.error(f"[FillAgg] Backfill error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})
