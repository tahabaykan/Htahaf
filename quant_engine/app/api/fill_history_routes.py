"""
Fill History API Routes — 7-Day Retrospective Fill Report

Reads persisted CSV files from data/logs/daily_fills/ to provide
a comprehensive retrospective view of all fills across accounts.

Key features:
- 7-day rolling window of fill history
- Day-by-day summary (total fills, buy/sell notional, unique symbols)
- Per-strategy/tag breakdown (LT_TRIM, MM, KARBOTU, ADDNEWPOS, JFIN, REV, etc.)
- Individual fill detail with bench_chg at fill time
- Survives restarts — reads from disk, not Redis
"""

import os
import csv
import glob
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.core.logger import logger

router = APIRouter(prefix="/api/fill-history", tags=["Fill History"])

FILLS_DIR = os.path.join("data", "logs", "daily_fills")


def _parse_date_from_filename(filename: str) -> Optional[str]:
    """Extract date from filename like hamfilledorders260225.csv -> 2026-02-25"""
    try:
        # Extract YYMMDD from filename 
        basename = os.path.basename(filename)
        # Find the 6-digit date portion (YYMMDD)
        # Patterns: hamfilledordersYYMMDD.csv, ibpedfilledordersYYMMDD.csv
        import re
        match = re.search(r'(\d{6})\.csv$', basename)
        if match:
            yymmdd = match.group(1)
            dt = datetime.strptime(yymmdd, "%y%m%d")
            return dt.strftime("%Y-%m-%d")
    except Exception:
        pass
    return None


def _extract_account_from_filename(filename: str) -> str:
    """Extract account type from filename."""
    basename = os.path.basename(filename).lower()
    if basename.startswith("ham"):
        return "HAMMER_PRO"
    elif "ped" in basename:
        return "IBKR_PED"
    elif "gun" in basename:
        return "IBKR_GUN"
    return "UNKNOWN"


def _read_fills_csv(filepath: str) -> List[Dict[str, Any]]:
    """Read a single fills CSV file and return normalized rows."""
    fills = []
    account = _extract_account_from_filename(filepath)
    date_str = _parse_date_from_filename(filepath)
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    qty = float(row.get("Quantity", 0) or 0)
                    price = float(row.get("Price", 0) or 0)
                    bid_str = row.get("Bid", "")
                    ask_str = row.get("Ask", "")
                    spread_str = row.get("Spread", "")
                    bench_str = row.get("Bench_Chg", "")
                    
                    fill = {
                        "date": date_str,
                        "time": row.get("Time", ""),
                        "symbol": row.get("Symbol", ""),
                        "action": row.get("Action", ""),
                        "quantity": qty,
                        "price": price,
                        "notional": round(qty * price, 2),
                        "strategy": row.get("Strategy", "UNKNOWN"),
                        "source": row.get("Source", ""),
                        "account": account,
                        "bid": float(bid_str) if bid_str else None,
                        "ask": float(ask_str) if ask_str else None,
                        "spread": float(spread_str) if spread_str else None,
                        "bench_chg": float(bench_str) if bench_str else None,
                        "bench_source": row.get("Bench_Source", ""),
                    }
                    fills.append(fill)
                except (ValueError, TypeError) as e:
                    continue
    except Exception as e:
        logger.warning(f"[FillHistory] Error reading {filepath}: {e}")
    
    return fills


def _get_available_dates(days: int = 7) -> List[str]:
    """Get list of dates that have fill files, within last N days."""
    cutoff = datetime.now() - timedelta(days=days)
    dates = set()
    
    if not os.path.exists(FILLS_DIR):
        return []
    
    for f in glob.glob(os.path.join(FILLS_DIR, "*filledorders*.csv")):
        date_str = _parse_date_from_filename(f)
        if date_str:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                if dt >= cutoff:
                    dates.add(date_str)
            except ValueError:
                continue
    
    return sorted(dates, reverse=True)


def _get_files_for_date(date_str: str) -> List[str]:
    """Get all fill CSV files for a specific date."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        yymmdd = dt.strftime("%y%m%d")
    except ValueError:
        return []
    
    files = []
    if os.path.exists(FILLS_DIR):
        for f in glob.glob(os.path.join(FILLS_DIR, f"*{yymmdd}.csv")):
            files.append(f)
    return files


def _get_current_prices(symbols: List[str]) -> Dict[str, float]:
    """Get current market prices for symbols from DataFabric/Redis."""
    prices = {}
    try:
        from app.core.data_fabric import get_data_fabric
        fabric = get_data_fabric()
        if fabric:
            for sym in symbols:
                snap = fabric.get_fast_snapshot(sym)
                if snap:
                    # Prefer last, then bid, then ask
                    price = snap.get('last') or snap.get('bid') or snap.get('ask')
                    if price and float(price) > 0:
                        prices[sym] = float(price)
    except Exception:
        pass
    
    # Fallback: try Redis market data cache
    if len(prices) < len(symbols):
        try:
            from app.core.redis_client import get_redis_client
            import json
            redis = get_redis_client()
            if redis:
                for sym in symbols:
                    if sym in prices:
                        continue
                    raw = redis.get(f"market_data:{sym}")
                    if raw:
                        data = json.loads(raw if isinstance(raw, str) else raw.decode())
                        price = data.get('last') or data.get('bid') or data.get('price')
                        if price and float(price) > 0:
                            prices[sym] = float(price)
        except Exception:
            pass
    
    return prices


def _build_day_summary(fills: List[Dict]) -> Dict[str, Any]:
    """Build summary statistics for a list of fills."""
    if not fills:
        return {
            "total_fills": 0,
            "buy_fills": 0,
            "sell_fills": 0,
            "buy_notional": 0,
            "sell_notional": 0,
            "net_notional": 0,
            "unique_symbols": 0,
            "symbols": [],
            "by_strategy": {},
            "by_account": {},
            "by_symbol": {},
            "total_realized_pnl": 0,
            "total_unrealized_pnl": 0,
            "total_pnl": 0,
        }
    
    buy_fills = [f for f in fills if f.get("action", "").upper() == "BUY"]
    sell_fills = [f for f in fills if f.get("action", "").upper() in ("SELL", "SHORT")]
    
    buy_notional = sum(f.get("notional", 0) for f in buy_fills)
    sell_notional = sum(f.get("notional", 0) for f in sell_fills)
    
    symbols = sorted(set(f.get("symbol", "") for f in fills if f.get("symbol")))
    
    # ═══════════════════════════════════════════════════════
    # BY SYMBOL: Per-symbol consolidated lot breakdown + P&L
    # ═══════════════════════════════════════════════════════
    symbol_data = defaultdict(lambda: {
        "buy_qty": 0.0,
        "sell_qty": 0.0,
        "buy_notional": 0.0,
        "sell_notional": 0.0,
        "fill_count": 0,
        "tags": set(),
        "bench_chg_values": [],
    })
    
    for f in fills:
        sym = f.get("symbol", "")
        if not sym:
            continue
        action = f.get("action", "").upper()
        qty = float(f.get("quantity", 0) or 0)
        price = float(f.get("price", 0) or 0)
        
        symbol_data[sym]["fill_count"] += 1
        
        tag = f.get("strategy", "UNKNOWN") or "UNKNOWN"
        symbol_data[sym]["tags"].add(tag)
        
        if f.get("bench_chg") is not None:
            symbol_data[sym]["bench_chg_values"].append(f["bench_chg"])
        
        if action == "BUY":
            symbol_data[sym]["buy_qty"] += qty
            symbol_data[sym]["buy_notional"] += qty * price
        elif action in ("SELL", "SHORT"):
            symbol_data[sym]["sell_qty"] += qty
            symbol_data[sym]["sell_notional"] += qty * price
    
    # Get current market prices for unrealized P&L
    current_prices = _get_current_prices(list(symbol_data.keys()))
    
    # Finalize per-symbol data
    by_symbol = {}
    total_realized_pnl = 0.0
    total_unrealized_pnl = 0.0
    
    for sym in sorted(symbol_data.keys()):
        d = symbol_data[sym]
        buy_qty = d["buy_qty"]
        sell_qty = d["sell_qty"]
        
        # VWAP (volume-weighted average price)
        avg_buy = (d["buy_notional"] / buy_qty) if buy_qty > 0 else 0
        avg_sell = (d["sell_notional"] / sell_qty) if sell_qty > 0 else 0
        
        # ── Realized P&L: matched (closed) lots ──
        matched_qty = min(buy_qty, sell_qty)
        realized_pnl = matched_qty * (avg_sell - avg_buy) if matched_qty > 0 else 0.0
        total_realized_pnl += realized_pnl
        
        # ── Unrealized P&L: remaining open lots ──
        remaining_qty = abs(buy_qty - sell_qty)
        cur_price = current_prices.get(sym)
        unrealized_pnl = None
        
        if remaining_qty > 0 and cur_price and cur_price > 0:
            if buy_qty > sell_qty:
                # Net long: holding extra bought lots
                unrealized_pnl = remaining_qty * (cur_price - avg_buy)
            else:
                # Net short: holding extra sold lots
                unrealized_pnl = remaining_qty * (avg_sell - cur_price)
            total_unrealized_pnl += (unrealized_pnl or 0)
        
        # Net direction
        net_qty = buy_qty - sell_qty  # positive=net long, negative=net short
        
        bench_vals = d["bench_chg_values"]
        
        entry = {
            "buy_qty": round(buy_qty, 2),
            "avg_buy_price": round(avg_buy, 4) if buy_qty > 0 else None,
            "sell_qty": round(sell_qty, 2),
            "avg_sell_price": round(avg_sell, 4) if sell_qty > 0 else None,
            "net_qty": round(net_qty, 2),
            "matched_qty": round(matched_qty, 2),
            "remaining_qty": round(remaining_qty, 2),
            "realized_pnl": round(realized_pnl, 2),
            "current_price": round(cur_price, 4) if cur_price else None,
            "unrealized_pnl": round(unrealized_pnl, 2) if unrealized_pnl is not None else None,
            "total_pnl": round(realized_pnl + (unrealized_pnl or 0), 2),
            "fill_count": d["fill_count"],
            "tags": sorted(d["tags"]),
            "avg_bench_chg": round(sum(bench_vals) / len(bench_vals), 4) if bench_vals else None,
        }
        by_symbol[sym] = entry
    
    # By strategy breakdown
    by_strategy = defaultdict(lambda: {
        "count": 0, "buy_count": 0, "sell_count": 0,
        "buy_notional": 0, "sell_notional": 0,
        "symbols": set(), "avg_bench_chg": []
    })
    
    for f in fills:
        strategy = f.get("strategy", "UNKNOWN") or "UNKNOWN"
        action = f.get("action", "").upper()
        notional = f.get("notional", 0)
        
        by_strategy[strategy]["count"] += 1
        by_strategy[strategy]["symbols"].add(f.get("symbol", ""))
        
        if action == "BUY":
            by_strategy[strategy]["buy_count"] += 1
            by_strategy[strategy]["buy_notional"] += notional
        elif action in ("SELL", "SHORT"):
            by_strategy[strategy]["sell_count"] += 1
            by_strategy[strategy]["sell_notional"] += notional
        
        if f.get("bench_chg") is not None:
            by_strategy[strategy]["avg_bench_chg"].append(f["bench_chg"])
    
    # Finalize strategy data
    strategy_summary = {}
    for strat, data in by_strategy.items():
        bench_values = data.pop("avg_bench_chg")
        data["symbols"] = sorted(data["symbols"])
        data["symbol_count"] = len(data["symbols"])
        data["buy_notional"] = round(data["buy_notional"], 2)
        data["sell_notional"] = round(data["sell_notional"], 2)
        data["net_notional"] = round(data["buy_notional"] - data["sell_notional"], 2)
        data["avg_bench_chg"] = round(sum(bench_values) / len(bench_values), 4) if bench_values else None
        strategy_summary[strat] = data
    
    # By account breakdown
    by_account = defaultdict(lambda: {"count": 0, "buy_notional": 0, "sell_notional": 0})
    for f in fills:
        acct = f.get("account", "UNKNOWN")
        by_account[acct]["count"] += 1
        action = f.get("action", "").upper()
        notional = f.get("notional", 0)
        if action == "BUY":
            by_account[acct]["buy_notional"] += notional
        elif action in ("SELL", "SHORT"):
            by_account[acct]["sell_notional"] += notional
    
    account_summary = {}
    for acct, data in by_account.items():
        data["buy_notional"] = round(data["buy_notional"], 2)
        data["sell_notional"] = round(data["sell_notional"], 2)
        data["net_notional"] = round(data["buy_notional"] - data["sell_notional"], 2)
        account_summary[acct] = data
    
    return {
        "total_fills": len(fills),
        "buy_fills": len(buy_fills),
        "sell_fills": len(sell_fills),
        "buy_notional": round(buy_notional, 2),
        "sell_notional": round(sell_notional, 2),
        "net_notional": round(buy_notional - sell_notional, 2),
        "unique_symbols": len(symbols),
        "symbols": symbols,
        "by_strategy": strategy_summary,
        "by_account": account_summary,
        "by_symbol": by_symbol,
        "total_realized_pnl": round(total_realized_pnl, 2),
        "total_unrealized_pnl": round(total_unrealized_pnl, 2),
        "total_pnl": round(total_realized_pnl + total_unrealized_pnl, 2),
    }


@router.get("/summary")
async def get_fill_history_summary(days: int = Query(default=7, ge=1, le=30)):
    """
    Get day-by-day fill summary for the last N days.
    
    Returns aggregate stats per day: fill count, buy/sell notional, 
    strategy breakdown, and benchmark data.
    """
    try:
        available_dates = _get_available_dates(days)
        
        daily_summaries = []
        grand_totals = {
            "total_fills": 0,
            "total_buy_notional": 0,
            "total_sell_notional": 0,
            "total_days": 0,
        }
        
        for date_str in available_dates:
            files = _get_files_for_date(date_str)
            all_fills = []
            for fp in files:
                all_fills.extend(_read_fills_csv(fp))
            
            if not all_fills:
                continue
            
            summary = _build_day_summary(all_fills)
            summary["date"] = date_str
            
            # Day of week
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                summary["day_name"] = dt.strftime("%A")
            except:
                summary["day_name"] = ""
            
            daily_summaries.append(summary)
            
            grand_totals["total_fills"] += summary["total_fills"]
            grand_totals["total_buy_notional"] += summary["buy_notional"]
            grand_totals["total_sell_notional"] += summary["sell_notional"]
            grand_totals["total_days"] += 1
        
        grand_totals["total_buy_notional"] = round(grand_totals["total_buy_notional"], 2)
        grand_totals["total_sell_notional"] = round(grand_totals["total_sell_notional"], 2)
        grand_totals["total_net_notional"] = round(
            grand_totals["total_buy_notional"] - grand_totals["total_sell_notional"], 2
        )
        
        return JSONResponse(content={
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "days_requested": days,
            "grand_totals": grand_totals,
            "daily": daily_summaries,
        })
    
    except Exception as e:
        logger.error(f"[FillHistory] Error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/day/{date_str}")
async def get_fills_for_day(
    date_str: str,
    account: Optional[str] = Query(default=None, description="Filter by account: HAMMER_PRO, IBKR_PED"),
    strategy: Optional[str] = Query(default=None, description="Filter by strategy tag"),
    symbol: Optional[str] = Query(default=None, description="Filter by symbol"),
):
    """
    Get detailed fill list for a specific date.
    
    Supports filtering by account, strategy tag, and symbol.
    Includes benchmark data (bench_chg, bench_source) at fill time.
    """
    try:
        files = _get_files_for_date(date_str)
        if not files:
            return JSONResponse(content={
                "success": True,
                "date": date_str,
                "message": f"No fill data found for {date_str}",
                "fills": [],
                "summary": _build_day_summary([]),
            })
        
        all_fills = []
        for fp in files:
            all_fills.extend(_read_fills_csv(fp))
        
        # Apply filters
        if account:
            all_fills = [f for f in all_fills if f.get("account", "").upper() == account.upper()]
        if strategy:
            all_fills = [f for f in all_fills if strategy.upper() in (f.get("strategy", "") or "").upper()]
        if symbol:
            all_fills = [f for f in all_fills if symbol.upper() in (f.get("symbol", "") or "").upper()]
        
        summary = _build_day_summary(all_fills)
        summary["date"] = date_str
        
        return JSONResponse(content={
            "success": True,
            "date": date_str,
            "filters": {
                "account": account,
                "strategy": strategy,
                "symbol": symbol,
            },
            "summary": summary,
            "fills": all_fills,
        })
    
    except Exception as e:
        logger.error(f"[FillHistory] Error for {date_str}: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/day/{date_str}/symbols")
async def get_symbol_summary_for_day(
    date_str: str,
    account: Optional[str] = Query(default=None, description="Filter by account"),
    sort_by: Optional[str] = Query(default="total_pnl", description="Sort field: total_pnl, realized_pnl, fill_count, buy_qty, sell_qty"),
):
    """
    Per-symbol consolidated fill report for a specific date.
    
    For each symbol shows:
    - Buy: total lots + avg fill price
    - Sell: total lots + avg fill price
    - Realized P&L (matched/closed lots)
    - Unrealized P&L (remaining open lots × current price delta)
    - Total P&L
    - Strategy tags used
    """
    try:
        files = _get_files_for_date(date_str)
        if not files:
            return JSONResponse(content={
                "success": True,
                "date": date_str,
                "message": f"No fill data found for {date_str}",
                "symbols": [],
                "totals": {"realized_pnl": 0, "unrealized_pnl": 0, "total_pnl": 0},
            })
        
        all_fills = []
        for fp in files:
            all_fills.extend(_read_fills_csv(fp))
        
        if account:
            all_fills = [f for f in all_fills if f.get("account", "").upper() == account.upper()]
        
        summary = _build_day_summary(all_fills)
        
        # Convert by_symbol dict to sorted list for cleaner output
        symbol_list = []
        for sym, data in summary.get("by_symbol", {}).items():
            data["symbol"] = sym
            symbol_list.append(data)
        
        # Sort
        sort_field = sort_by or "total_pnl"
        reverse = True
        if sort_field in ("total_pnl", "realized_pnl", "unrealized_pnl"):
            # P&L: best first (highest)
            symbol_list.sort(key=lambda x: x.get(sort_field) or 0, reverse=True)
        elif sort_field == "fill_count":
            symbol_list.sort(key=lambda x: x.get("fill_count", 0), reverse=True)
        elif sort_field == "buy_qty":
            symbol_list.sort(key=lambda x: x.get("buy_qty", 0), reverse=True)
        elif sort_field == "sell_qty":
            symbol_list.sort(key=lambda x: x.get("sell_qty", 0), reverse=True)
        
        return JSONResponse(content={
            "success": True,
            "date": date_str,
            "unique_symbols": len(symbol_list),
            "total_fills": summary["total_fills"],
            "totals": {
                "buy_notional": summary["buy_notional"],
                "sell_notional": summary["sell_notional"],
                "realized_pnl": summary["total_realized_pnl"],
                "unrealized_pnl": summary["total_unrealized_pnl"],
                "total_pnl": summary["total_pnl"],
            },
            "symbols": symbol_list,
        })
    
    except Exception as e:
        logger.error(f"[FillHistory] Symbol summary error for {date_str}: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/strategy-breakdown")
async def get_strategy_breakdown(days: int = Query(default=7, ge=1, le=30)):
    """
    Get aggregated strategy breakdown across all days.
    
    Shows which strategy tags generated the most fills,
    their buy/sell balance, and average benchmark performance.
    """
    try:
        available_dates = _get_available_dates(days)
        
        # Aggregate all fills
        all_fills = []
        for date_str in available_dates:
            files = _get_files_for_date(date_str)
            for fp in files:
                all_fills.extend(_read_fills_csv(fp))
        
        if not all_fills:
            return JSONResponse(content={
                "success": True,
                "days": days,
                "strategies": {},
                "message": "No fill data available",
            })
        
        # Build per-strategy stats
        strategies = defaultdict(lambda: {
            "total_fills": 0,
            "buy_fills": 0,
            "sell_fills": 0,
            "buy_notional": 0.0,
            "sell_notional": 0.0,
            "symbols": set(),
            "days_active": set(),
            "bench_chg_values": [],
        })
        
        for f in all_fills:
            strat = f.get("strategy", "UNKNOWN") or "UNKNOWN"
            action = f.get("action", "").upper()
            notional = f.get("notional", 0)
            
            strategies[strat]["total_fills"] += 1
            strategies[strat]["symbols"].add(f.get("symbol", ""))
            strategies[strat]["days_active"].add(f.get("date", ""))
            
            if action == "BUY":
                strategies[strat]["buy_fills"] += 1
                strategies[strat]["buy_notional"] += notional
            elif action in ("SELL", "SHORT"):
                strategies[strat]["sell_fills"] += 1
                strategies[strat]["sell_notional"] += notional
            
            if f.get("bench_chg") is not None:
                strategies[strat]["bench_chg_values"].append(f["bench_chg"])
        
        # Finalize
        result = {}
        for strat, data in sorted(strategies.items(), key=lambda x: x[1]["total_fills"], reverse=True):
            bench_vals = data.pop("bench_chg_values")
            result[strat] = {
                "total_fills": data["total_fills"],
                "buy_fills": data["buy_fills"],
                "sell_fills": data["sell_fills"],
                "buy_notional": round(data["buy_notional"], 2),
                "sell_notional": round(data["sell_notional"], 2),
                "net_notional": round(data["buy_notional"] - data["sell_notional"], 2),
                "unique_symbols": len(data["symbols"]),
                "days_active": len(data["days_active"]),
                "avg_bench_chg": round(sum(bench_vals) / len(bench_vals), 4) if bench_vals else None,
                "bench_data_pct": round(len(bench_vals) / data["total_fills"] * 100, 1) if data["total_fills"] > 0 else 0,
            }
        
        return JSONResponse(content={
            "success": True,
            "days": days,
            "total_fills": len(all_fills),
            "strategies": result,
        })
    
    except Exception as e:
        logger.error(f"[FillHistory] Strategy breakdown error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/dates")
async def get_available_dates_endpoint(days: int = Query(default=7, ge=1, le=30)):
    """List all available dates with fill data."""
    try:
        dates = _get_available_dates(days)
        date_info = []
        for d in dates:
            files = _get_files_for_date(d)
            accounts = [_extract_account_from_filename(f) for f in files]
            
            # Quick count without full parse
            total_lines = 0
            for f in files:
                try:
                    with open(f, 'r') as fh:
                        total_lines += sum(1 for _ in fh) - 1  # minus header
                except:
                    pass
            
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
                day_name = dt.strftime("%A")
            except:
                day_name = ""
            
            date_info.append({
                "date": d,
                "day_name": day_name,
                "accounts": sorted(set(accounts)),
                "approx_fills": max(0, total_lines),
            })
        
        return JSONResponse(content={
            "success": True,
            "dates": date_info,
        })
    
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
