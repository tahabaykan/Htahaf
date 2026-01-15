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
    - Bench @Fill, Bench Now
    - Outperform Chg
    """
    try:
        # Get active trading account
        mode_mgr = get_account_mode_manager()
        active_account = mode_mgr.current_mode.value
        
        csv_mgr = get_qebench_csv(account=active_account)
        bench_fetcher = get_benchmark_fetcher()
        
        # Get all position states from CSV (only positions with bench@fill)
        position_states = csv_mgr.get_all_positions()
        
        # Get current positions from PositionSnapshotAPI for live prices
        from app.psfalgo.position_snapshot_api import get_position_snapshot_api
        pos_api = get_position_snapshot_api()
        
        mode_mgr = get_account_mode_manager()
        account_id = mode_mgr.current_mode.value if mode_mgr else 'HAMPRO'
        
        current_positions = await pos_api.get_position_snapshot(account_id=account_id)
        # Convert PositionSnapshot objects to dict
        current_pos_map = {p.symbol: p for p in current_positions}
        
        # Build response (only positions that exist in CSV)
        qebench_positions = []
        
        for state in position_states:
            symbol = state['symbol']
            
            # Get current market data from PositionSnapshot
            current_pos = current_pos_map.get(symbol)
            if current_pos:
                current_price = getattr(current_pos, 'current_price', 0.0) or 0.0
                prev_close = getattr(current_pos, 'prev_close', 0.0) or 0.0
                bid = getattr(current_pos, 'bid', 0.0) or 0.0
                ask = getattr(current_pos, 'ask', 0.0) or 0.0
            else:
                current_price = 0.0
                prev_close = 0.0
                bid = 0.0
                ask = 0.0
            
            # Get current benchmark
            bench_now = bench_fetcher.get_current_benchmark_price(symbol)
            if bench_now is None:
                bench_now = state['weighted_bench_fill']  # Fallback
            
            # Calculate metrics
            daily_chg = current_price - prev_close if prev_close > 0 else 0.0
            spread = ask - bid if ask > 0 and bid > 0 else 0.0
            
            outperform = calculate_outperform(
                current_price,
                state['weighted_avg_cost'],
                bench_now,
                state['weighted_bench_fill']
            )
            
            qebench_positions.append({
                'symbol': symbol,
                'qty': state['total_qty'],
                'avg_cost': round(state['weighted_avg_cost'], 2),
                'prev_close': round(prev_close, 2),
                'daily_chg': round(daily_chg, 2),
                'current_price': round(current_price, 2),
                'bid': round(bid, 2),
                'ask': round(ask, 2),
                'spread': round(spread, 2),
                'bench_at_fill': round(state['weighted_bench_fill'], 2),
                'bench_now': round(bench_now, 2),
                'outperform_chg': round(outperform, 2)
            })
        
        logger.info(f"[QeBench API] Returning {len(qebench_positions)} positions")
        
        return {
            'success': True,
            'positions': qebench_positions
        }
        
    except Exception as e:
        logger.error(f"[QeBench API] Error: {e}")
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
        
        # Get all position states from CSV
        position_states = csv_mgr.get_all_positions()
        
        # Get current positions from PositionSnapshotAPI
        from app.psfalgo.position_snapshot_api import get_position_snapshot_api
        pos_api = get_position_snapshot_api()
        current_positions = await pos_api.get_position_snapshot(account_id=active_account)
        current_pos_map = {p.symbol: p for p in current_positions}
        
        reset_count = 0
        
        for state in position_states:
            symbol = state['symbol']
            
            # Get current price and bench from PositionSnapshot
            current_pos = current_pos_map.get(symbol)
            current_price = getattr(current_pos, 'current_price', 0.0) if current_pos else 0.0
            
            bench_now = bench_fetcher.get_current_benchmark_price(symbol)
            if bench_now is None:
                logger.warning(f"[QeBench] No bench price for {symbol}, skipping reset")
                continue
            
            # Calculate new bench@fill that makes outperform = 0
            new_bench_fill = calculate_reset_bench_fill(
                current_price,
                state['weighted_avg_cost'],
                bench_now
            )
            
            # Update CSV
            csv_mgr.reset_position_bench_fill(symbol, new_bench_fill)
            reset_count += 1
        
        logger.info(f"[QeBench API] Reset {reset_count} positions")
        
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
