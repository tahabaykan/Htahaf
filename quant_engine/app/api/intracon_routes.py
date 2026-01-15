"""
IntraCon API Routes

Intraday Controller dashboard and control endpoints.
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import Optional, Dict, Any, List
import json

from app.core.logger import logger

router = APIRouter(prefix="/api/intracon", tags=["IntraCon"])


@router.get("/status")
async def get_intracon_status():
    """
    Get IntraCon engine status and summary.
    """
    from app.psfalgo.intracon import get_intracon_engine
    
    engine = get_intracon_engine()
    if not engine:
        return {
            "success": False,
            "initialized": False,
            "message": "IntraCon engine not initialized"
        }
    
    # Get snapshots for all modes
    modes_status = {}
    for mode in ['hampro', 'ibkr_ped', 'ibkr_gun']:
        snapshot = engine.get_snapshot(mode)
        if snapshot:
            modes_status[mode] = {
                "initialized": True,
                "snapshot_date": snapshot.snapshot_date,
                "snapshot_time": snapshot.snapshot_time,
                "symbol_count": len(snapshot.symbols),
                "total_portfolio_lots": snapshot.total_portfolio_lots,
                "total_portfolio_value": snapshot.total_portfolio_value
            }
        else:
            modes_status[mode] = {"initialized": False}
    
    return {
        "success": True,
        "initialized": True,
        "modes": modes_status
    }


@router.post("/initialize/{mode}")
async def initialize_intracon(mode: str):
    """
    Initialize IntraCon for a specific mode.
    
    This pulls data from BEFDAY snapshot and current positions.
    """
    valid_modes = ['hampro', 'ibkr_ped', 'ibkr_gun']
    if mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Must be one of: {valid_modes}")
    
    try:
        from app.psfalgo.intracon import get_intracon_engine, initialize_intracon_engine
        from app.api.befday_routes import BEFDAY_DIR, get_today_str
        from app.market_data.static_data_store import get_static_store
        
        # Ensure engine exists
        engine = get_intracon_engine()
        if not engine:
            initialize_intracon_engine()
            engine = get_intracon_engine()
        
        # Load BEFDAY positions
        befday_positions = []
        today = get_today_str()
        account_map = {'hampro': 'ham', 'ibkr_ped': 'ibped', 'ibkr_gun': 'ibgun'}
        account = account_map.get(mode, 'ham')
        
        import os
        befday_file = os.path.join(BEFDAY_DIR, f"bef{account}_{today}.json")
        if os.path.exists(befday_file):
            with open(befday_file, 'r', encoding='utf-8') as f:
                befday_data = json.load(f)
                befday_positions = befday_data.get('positions', [])
        
        # Get current positions
        current_positions = []
        try:
            from app.live.hammer_feed import get_hammer_feed
            feed = get_hammer_feed()
            if feed and hasattr(feed, 'positions'):
                for sym, pos in feed.positions.items():
                    qty = pos.get('quantity', 0)
                    if qty != 0:
                        current_positions.append({
                            'symbol': sym,
                            'qty': qty,
                            'avg_cost': pos.get('avg_cost', 0),
                            'current_price': pos.get('last_price', pos.get('avg_cost', 0))
                        })
        except Exception as e:
            logger.warning(f"[INTRACON] Could not get live positions: {e}")
        
        # Get static data (for MAXALW)
        static_store = get_static_store()
        static_data = {}
        if static_store:
            for sym in set([p.get('symbol') or p.get('Symbol') for p in befday_positions + current_positions if p]):
                if sym:
                    sd = static_store.get_static_data(sym)
                    if sd:
                        static_data[sym] = sd
        
        # Calculate total portfolio value
        total_value = sum(
            abs(p.get('qty', 0)) * p.get('current_price', p.get('avg_cost', 25))
            for p in current_positions
        )
        
        # Initialize
        snapshot = engine.initialize(
            mode=mode,
            befday_positions=befday_positions,
            current_positions=current_positions,
            static_data=static_data,
            total_portfolio_value=total_value
        )
        
        return {
            "success": True,
            "mode": mode,
            "snapshot_date": snapshot.snapshot_date,
            "symbol_count": len(snapshot.symbols),
            "total_portfolio_lots": snapshot.total_portfolio_lots,
            "total_portfolio_value": snapshot.total_portfolio_value,
            "befday_positions_loaded": len(befday_positions),
            "current_positions_loaded": len(current_positions)
        }
        
    except Exception as e:
        logger.error(f"[INTRACON] Initialize error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/symbols/{mode}")
async def get_intracon_symbols(mode: str):
    """
    Get all symbols with their intraday state for a mode.
    """
    from app.psfalgo.intracon import get_intracon_engine
    
    engine = get_intracon_engine()
    if not engine:
        raise HTTPException(status_code=400, detail="IntraCon not initialized")
    
    snapshot = engine.get_snapshot(mode)
    if not snapshot:
        raise HTTPException(status_code=400, detail=f"No snapshot for mode: {mode}")
    
    symbols = engine.get_all_symbols_summary(mode)
    
    return {
        "success": True,
        "mode": mode,
        "snapshot_date": snapshot.snapshot_date,
        "snapshot_time": snapshot.snapshot_time,
        "total_portfolio_lots": snapshot.total_portfolio_lots,
        "symbol_count": len(symbols),
        "symbols": symbols
    }


@router.get("/symbol/{mode}/{symbol}")
async def get_symbol_state(mode: str, symbol: str):
    """
    Get intraday state for a specific symbol.
    """
    from app.psfalgo.intracon import get_intracon_engine
    
    engine = get_intracon_engine()
    if not engine:
        raise HTTPException(status_code=400, detail="IntraCon not initialized")
    
    intraday = engine.get_symbol_state(symbol, mode)
    if not intraday:
        return {
            "success": False,
            "symbol": symbol,
            "mode": mode,
            "found": False,
            "message": f"No data for {symbol} in {mode}"
        }
    
    return {
        "success": True,
        "symbol": symbol,
        "mode": mode,
        "found": True,
        "data": intraday.to_dict()
    }


@router.post("/check-add/{mode}/{symbol}")
async def check_add_position(mode: str, symbol: str, lot: int = 200):
    """
    Check if a position add is allowed based on daily limits.
    
    Args:
        mode: Trading mode
        symbol: Symbol to add
        lot: Requested lot to add
    """
    from app.psfalgo.intracon import get_intracon_engine
    
    engine = get_intracon_engine()
    if not engine:
        raise HTTPException(status_code=400, detail="IntraCon not initialized")
    
    allowed, adjusted_lot, reason = engine.check_add_position(symbol, lot, mode)
    
    intraday = engine.get_symbol_state(symbol, mode)
    
    return {
        "success": True,
        "symbol": symbol,
        "mode": mode,
        "requested_lot": lot,
        "allowed": allowed,
        "adjusted_lot": adjusted_lot,
        "reason": reason,
        "state": intraday.to_dict() if intraday else None
    }
