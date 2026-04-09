"""
Fill Report API Routes

Provides enriched fill data for the Operations Fill Report page.
Combines DailyFillsStore data with QeBench benchmark calculations
to provide a comprehensive execution quality analysis.
"""
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from typing import Dict, List, Any, Optional
from datetime import datetime

from app.core.logger import logger

router = APIRouter(prefix="/api/fill-report", tags=["Fill Report"])


def _get_fills_for_account(account_type: str) -> List[Dict]:
    """Get today's fills from DailyFillsStore."""
    try:
        from app.trading.daily_fills_store import get_daily_fills_store
        store = get_daily_fills_store()
        return store.get_all_fills(account_type)
    except Exception as e:
        logger.error(f"[FillReport] Error getting fills for {account_type}: {e}")
        return []


def _get_current_market_data(symbol: str) -> Dict:
    """Get current bid/ask/last from market data cache."""
    # Primary: thread-safe getter
    try:
        from app.api.market_data_routes import get_market_data
        data = get_market_data(symbol)
        if data:
            return {
                "bid_now": data.get('bid'),
                "ask_now": data.get('ask'),
                "last_now": data.get('last') or data.get('lastPrice'),
                "prev_close": data.get('prev_close') or data.get('prevClose'),
            }
    except Exception:
        pass
    
    # Fallback: direct cache access
    try:
        from app.api.market_data_routes import market_data_cache
        if market_data_cache and symbol in market_data_cache:
            cached = market_data_cache[symbol]
            return {
                "bid_now": cached.get('bid'),
                "ask_now": cached.get('ask'),
                "last_now": cached.get('last') or cached.get('lastPrice'),
                "prev_close": cached.get('prev_close') or cached.get('prevClose'),
            }
    except Exception:
        pass
    
    return {}


def _enrich_fill(fill: Dict) -> Dict:
    """Enrich a single fill with current market data and fill quality metrics."""
    symbol = fill.get("symbol", "")
    price = float(fill.get("price", 0))
    action = (fill.get("action", "") or "").upper()
    bid_at_fill = fill.get("bid")
    ask_at_fill = fill.get("ask")
    spread_at_fill = fill.get("spread")
    
    # Get current market data for comparison
    current = _get_current_market_data(symbol)
    fill.update({
        "bid_now": current.get("bid_now"),
        "ask_now": current.get("ask_now"),
        "last_now": current.get("last_now"),
        "prev_close": current.get("prev_close"),
    })
    
    # Fill Quality Analysis
    if bid_at_fill is not None and ask_at_fill is not None and price > 0:
        bid_f = float(bid_at_fill)
        ask_f = float(ask_at_fill)
        spread = ask_f - bid_f if ask_f > bid_f else 0
        mid = (bid_f + ask_f) / 2 if bid_f > 0 else price
        
        if action == "BUY":
            # BUY: lower is better. At bid = perfect, at ask = worst
            if spread > 0:
                # 0 = bought at ask, 1 = bought at bid
                quality_pct = max(0, min(1, (ask_f - price) / spread)) * 100
            else:
                quality_pct = 50  # No spread info
            fill["fill_quality_pct"] = round(quality_pct, 1)
            fill["fill_quality"] = "EXCELLENT" if quality_pct >= 80 else "GOOD" if quality_pct >= 50 else "FAIR" if quality_pct >= 20 else "POOR"
            fill["vs_mid"] = round(price - mid, 4)  # Negative = better for buy
        
        elif action in ("SELL", "SHORT"):
            # SELL: higher is better. At ask = perfect, at bid = worst
            if spread > 0:
                # 0 = sold at bid, 1 = sold at ask
                quality_pct = max(0, min(1, (price - bid_f) / spread)) * 100
            else:
                quality_pct = 50
            fill["fill_quality_pct"] = round(quality_pct, 1)
            fill["fill_quality"] = "EXCELLENT" if quality_pct >= 80 else "GOOD" if quality_pct >= 50 else "FAIR" if quality_pct >= 20 else "POOR"
            fill["vs_mid"] = round(price - mid, 4)  # Positive = better for sell
    
    # P&L since fill (current vs fill price)
    last_now = current.get("last_now")
    if last_now and price > 0:
        last_f = float(last_now)
        if action == "BUY":
            fill["pnl_since_fill"] = round(last_f - price, 4)
            fill["pnl_since_fill_pct"] = round((last_f - price) / price * 100, 2)
        elif action in ("SELL", "SHORT"):
            fill["pnl_since_fill"] = round(price - last_f, 4)
            fill["pnl_since_fill_pct"] = round((price - last_f) / price * 100, 2)
    
    return fill


@router.get("/today")
async def get_todays_fill_report():
    """
    Get comprehensive fill report for today across all accounts.
    
    Returns enriched fill data with:
    - Fill time, symbol, action, qty, price
    - Bid/Ask at fill time
    - Spread at fill time
    - Fill quality score (0-100%)
    - Current market data comparison
    - P&L since fill
    - Benchmark change (QeBench)
    """
    try:
        accounts = ["HAMMER_PRO", "IBKR_PED"]
        all_fills = []
        per_account = {}
        
        for acct in accounts:
            fills = _get_fills_for_account(acct)
            enriched = [_enrich_fill(f) for f in fills]
            
            # Add account identifier
            for f in enriched:
                f["account"] = acct
            
            per_account[acct] = {
                "fills": enriched,
                "count": len(enriched),
                "buy_count": sum(1 for f in enriched if f.get("action", "").upper() == "BUY"),
                "sell_count": sum(1 for f in enriched if f.get("action", "").upper() in ("SELL", "SHORT")),
            }
            all_fills.extend(enriched)
        
        # Sort all fills by time (newest first)
        all_fills.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
        
        # Calculate summary stats
        total_fills = len(all_fills)
        total_buy_value = sum(
            float(f.get("qty", 0)) * float(f.get("price", 0))
            for f in all_fills if f.get("action", "").upper() == "BUY"
        )
        total_sell_value = sum(
            float(f.get("qty", 0)) * float(f.get("price", 0))
            for f in all_fills if f.get("action", "").upper() in ("SELL", "SHORT")
        )
        
        # Average fill quality
        quality_scores = [f["fill_quality_pct"] for f in all_fills if "fill_quality_pct" in f]
        avg_quality = round(sum(quality_scores) / len(quality_scores), 1) if quality_scores else None
        
        # Unique symbols
        unique_symbols = list(set(f.get("symbol", "") for f in all_fills if f.get("symbol")))
        
        return JSONResponse(content={
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "date": datetime.now().strftime("%Y-%m-%d"),
            "summary": {
                "total_fills": total_fills,
                "total_buy_value": round(total_buy_value, 2),
                "total_sell_value": round(total_sell_value, 2),
                "net_value": round(total_buy_value - total_sell_value, 2),
                "avg_fill_quality": avg_quality,
                "unique_symbols": len(unique_symbols),
                "symbols": sorted(unique_symbols),
            },
            "fills": all_fills,
            "per_account": per_account,
        })
    
    except Exception as e:
        logger.error(f"[FillReport] Error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/today/{account_id}")
async def get_account_fill_report(account_id: str):
    """Get fill report for a specific account."""
    try:
        fills = _get_fills_for_account(account_id)
        enriched = [_enrich_fill(f) for f in fills]
        
        for f in enriched:
            f["account"] = account_id
        
        return JSONResponse(content={
            "success": True,
            "account": account_id,
            "timestamp": datetime.now().isoformat(),
            "fills": enriched,
            "count": len(enriched),
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
