"""
QeBench API Routes

Endpoints for QeBench benchmark tracking system.
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict
from loguru import logger

from app.qebench import get_qebench_csv
from app.qebench.calculator import calculate_outperform, calculate_reset_bench_fill
from app.qebench.benchmark import get_benchmark_fetcher
from app.psfalgo.account_mode import get_account_mode_manager

router = APIRouter(prefix="/api/qebench", tags=["QeBench"])


@router.get("/positions")
async def get_qebench_positions():
    """
    Get all positions with QeBench data.
    
    Returns position table with:
    - Symbol, Qty, Avg Cost
    - Current price, Bid, Ask, Spread
    - Bench @Fill, Bench Now (if available from CSV)
    - Outperform Chg (if bench data available)
    
    NEW: Shows ALL positions from account, CSV data is optional enrichment
    """
    try:
        # Get active trading account
        mode_mgr = get_account_mode_manager()
        active_account = mode_mgr.current_mode.value
        
        csv_mgr = get_qebench_csv(account=active_account)
        bench_fetcher = get_benchmark_fetcher()
        
        # Get CSV position states (positions with bench@fill) - Optional enrichment
        csv_position_states = csv_mgr.get_all_positions()
        csv_state_map = {state['symbol']: state for state in csv_position_states}
        
        # Get current positions from PositionSnapshotAPI (PRIMARY SOURCE)
        from app.psfalgo.position_snapshot_api import get_position_snapshot_api
        pos_api = get_position_snapshot_api()
        
        mode_mgr = get_account_mode_manager()
        account_id = mode_mgr.current_mode.value if mode_mgr else 'HAMPRO'
        
        current_positions = await pos_api.get_position_snapshot(account_id=account_id)
        
        # Build response for ALL current positions
        qebench_positions = []
        
        for current_pos in current_positions:
            symbol = current_pos.symbol
            
            # Get live market data
            current_price = getattr(current_pos, 'current_price', 0.0) or 0.0
            prev_close = getattr(current_pos, 'prev_close', 0.0) or 0.0
            bid = getattr(current_pos, 'bid', 0.0) or 0.0
            ask = getattr(current_pos, 'ask', 0.0) or 0.0
            qty = getattr(current_pos, 'qty', 0.0) or 0.0
            avg_cost = getattr(current_pos, 'avg_price', 0.0) or 0.0
            
            # Calculate basic metrics
            daily_chg = current_price - prev_close if prev_close > 0 else 0.0
            spread = ask - bid if ask > 0 and bid > 0 else 0.0
            
            # Enrich with CSV data if available
            csv_state = csv_state_map.get(symbol)
            if csv_state:
                # Has benchmark data
                bench_at_fill = csv_state['weighted_bench_fill']
                bench_now = bench_fetcher.get_current_benchmark_price(symbol)
                if bench_now is None:
                    bench_now = bench_at_fill  # Fallback
                
                outperform = calculate_outperform(
                    current_price,
                    avg_cost,
                    bench_now,
                    bench_at_fill
                )
            else:
                # No benchmark data yet
                bench_at_fill = 0.0
                bench_now = bench_fetcher.get_current_benchmark_price(symbol) or 0.0
                outperform = 0.0
            
            qebench_positions.append({
                'symbol': symbol,
                'qty': round(qty, 2),
                'avg_cost': round(avg_cost, 2),
                'prev_close': round(prev_close, 2),
                'daily_chg': round(daily_chg, 2),
                'current_price': round(current_price, 2),
                'bid': round(bid, 2),
                'ask': round(ask, 2),
                'spread': round(spread, 2),
                'bench_at_fill': round(bench_at_fill, 2),
                'bench_now': round(bench_now, 2),
                'outperform_chg': round(outperform, 2)
            })
        
        logger.info(f"[QeBench API] Returning {len(qebench_positions)} positions (CSV enriched: {len(csv_state_map)})")
        
        return {
            'success': True,
            'positions': qebench_positions
        }
        
    except Exception as e:
        logger.error(f"[QeBench API] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset-all")
async def reset_all_outperforms():
    """
    Reset all outperform values to 0 by recalculating bench@fill.
    
    Makes all positions appear as if opened "right now".
    """
    try:
        # Get active trading account
        mode_mgr = get_account_mode_manager()
        active_account = mode_mgr.current_mode.value
        
        csv_mgr = get_qebench_csv(account=active_account)
        bench_fetcher = get_benchmark_fetcher()
        
        # Get current positions from PositionSnapshotAPI
        from app.psfalgo.position_snapshot_api import get_position_snapshot_api
        pos_api = get_position_snapshot_api()
        current_positions = await pos_api.get_position_snapshot(account_id=active_account)
        
        reset_count = 0
        
        for pos in current_positions:
            symbol = pos.symbol
            
            # Skip if critical data missing
            current_price = getattr(pos, 'current_price', 0.0) or 0.0
            avg_cost = getattr(pos, 'avg_price', 0.0) or 0.0
            qty = getattr(pos, 'qty', 0) or 0
            
            if current_price <= 0 or avg_cost <= 0:
                logger.warning(f"[QeBench] Skipping reset for {symbol}: price={current_price}, cost={avg_cost}")
                continue
                
            bench_now = bench_fetcher.get_current_benchmark_price(symbol)
            if bench_now is None or bench_now <= 0:
                logger.warning(f"[QeBench] No bench price for {symbol}, default to 0 outperform")
                # If no bench, we can't really do relative performance.
                # But to stop errors, maybe init with current price? 
                # Better to skip and wait for Bench Now to appear.
                continue
            
            # Calculate new bench@fill that makes outperform = 0
            # Formula: Outperform = (Price - Cost) - (BenchNow - BenchFill)
            # 0 = (P - C) - (Bn - Bf)
            # Bf = Bn - (P - C)
            price_diff = current_price - avg_cost
            new_bench_fill = bench_now - price_diff
            
            # Update/Create in CSV
            # valid_date string
            import datetime
            now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            csv_mgr.update_position(
                symbol=symbol,
                total_qty=qty,
                weighted_avg_cost=avg_cost,
                weighted_bench_fill=new_bench_fill
            )
            reset_count += 1
        
        logger.info(f"[QeBench API] Reset {reset_count} positions (Initialized Bench@Fill)")
        
        return {
            'success': True,
            'message': f'Reset {reset_count} positions',
            'reset_count': reset_count
        }
        
    except Exception as e:
        logger.error(f"[QeBench API] Reset error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fills")
async def get_qebench_fills(symbol: str = None, limit: int = 100):
    """
    Get fill history with benchmark data.
    
    Args:
        symbol: Optional filter by symbol
        limit: Max records to return
    """
    try:
        # Get active trading account
        mode_mgr = get_account_mode_manager()
        active_account = mode_mgr.current_mode.value
        
        csv_mgr = get_qebench_csv(account=active_account)
        
        if symbol:
            fills = csv_mgr.get_fills_for_symbol(symbol)
        else:
            fills = []  # CSV doesn't have "today" filter, return empty for now
        
        fills = fills[:limit]
        
        return {
            'success': True,
            'fills': fills
        }
        
    except Exception as e:
        logger.error(f"[QeBench API] Error fetching fills: {e}")
        raise HTTPException(status_code=500, detail=str(e))
