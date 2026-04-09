"""
Simulation API Routes

Endpoints for controlling simulation mode and fake order management.

Safety: All simulation endpoints check that LIFELESS mode is active.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List
from pydantic import BaseModel

from app.core.simulation_controller import get_simulation_controller
from app.simulation.fake_order_tracker import get_fake_order_tracker, reset_fake_order_tracker
from app.simulation.fill_simulator import get_fill_simulator
from app.core.logger import logger


router = APIRouter(prefix="/api/simulation", tags=["simulation"])


class SimulationStatusResponse(BaseModel):
    """Simulation status response"""
    simulation_active: bool
    lifeless_active: bool
    is_simulation_mode: bool
    mode_display: str
    pending_orders: int
    filled_orders: int
    total_orders: int


class FillRequest(BaseModel):
    """Fill simulation request"""
    fill_percentage: float = 0.5
    min_fills: int = 1
    max_slippage: float = 0.02


@router.post("/enable")
async def enable_simulation():
    """
    Enable simulation mode.
    
    Safety: Only works if LIFELESS mode is active.
    """
    try:
        controller = get_simulation_controller()
        controller.enable_simulation()  # Raises error if not in LIFELESS
        
        # Start FillSimulator background worker
        try:
            from app.simulation.fill_simulator import start_fill_simulator
            await start_fill_simulator()
            logger.info("[API] FillSimulator started")
        except Exception as e:
            logger.warning(f"[API] Could not start FillSimulator: {e}")
        
        logger.info("[API] Simulation mode ENABLED")
        
        return {
            "status": "enabled",
            "message": "🎭 Simulation mode active - orders will be FAKE"
        }
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] Error enabling simulation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/disable")
async def disable_simulation():
    """Disable simulation mode"""
    try:
        controller = get_simulation_controller()
        controller.disable_simulation()
        
        # Stop FillSimulator background worker
        try:
            from app.simulation.fill_simulator import stop_fill_simulator
            await stop_fill_simulator()
            logger.info("[API] FillSimulator stopped")
        except Exception as e:
            logger.warning(f"[API] Could not stop FillSimulator: {e}")
        
        logger.info("[API] Simulation mode DISABLED")
        
        return {
            "status": "disabled",
            "message": "💰 Real mode active - orders will be REAL"
        }
    
    except Exception as e:
        logger.error(f"[API] Error disabling simulation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/set-lifeless")
async def set_lifeless_mode(active: bool = Query(..., description="Enable/disable LIFELESS mode")):
    """
    Set LIFELESS mode state.
    
    Called by UI when LIFELESS toggle changes.
    """
    try:
        controller = get_simulation_controller()
        controller.set_lifeless_mode(active)
        
        # Also notify DataFabric to enable lifeless mode
        from app.core.data_fabric import DataFabric
        fabric = DataFabric()
        fabric.set_lifeless_mode(active)
        
        logger.info(f"[API] LIFELESS mode: {active}")
        
        return {
            "lifeless_active": active,
            "simulation_active": controller.simulation_active,
            "message": f"LIFELESS mode: {'ON' if active else 'OFF'}"
        }
    
    except Exception as e:
        logger.error(f"[API] Error setting LIFELESS mode: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=SimulationStatusResponse)
async def get_simulation_status():
    """Get current simulation status"""
    try:
        controller = get_simulation_controller()
        tracker = get_fake_order_tracker()
        stats = tracker.get_stats()
        status = controller.get_status()
        
        # Inject Global Execution Mode awareness
        try:
            from app.state.runtime_controls import get_runtime_controls_manager
            controls_mgr = get_runtime_controls_manager()
            # Default account context usually determines checking, but for UI status text we can check 'IBKR_PED' or similar
            # Or just check the global Default
            global_mode = controls_mgr.get_controls("default").execution_mode
            
            # Check priorities:
            # 1. Simulation Mode (Execution + Data)
            # 2. Lifeless Mode (Data only) -> "LIFELESS DATA"
            # 3. Real Data -> Check Global Execution Mode (Preview vs Live)
            
            if status['is_simulation_mode']:
                status['mode_display'] = '🎭 SIMULATION'
            elif status['lifeless_active']:
                status['mode_display'] = '🧪 LIFELESS DATA (Fake)'
            else:
                # Real Data Flow
                if global_mode == 'PREVIEW':
                    status['mode_display'] = '🛡️ PREVIEW (Safe)'
                elif global_mode == 'LIVE':
                    status['mode_display'] = '📡 LIVE EXECUTION'
                else:
                    status['mode_display'] = f'📡 {global_mode}'

        except Exception as e:
            logger.warning(f"[API] Could not check global mode: {e}")
            # Fallback handled by controller (returns 'REAL' or 'SIMULATION')
            if status['mode_display'] == '💰 REAL':
                 status['mode_display'] = '📡 LIVE DATA'

        return SimulationStatusResponse(
            simulation_active=status['simulation_active'],
            lifeless_active=status['lifeless_active'],
            is_simulation_mode=status['is_simulation_mode'],
            mode_display=status['mode_display'],
            pending_orders=stats['pending'],
            filled_orders=stats['filled'],
            total_orders=stats['total_orders']
        )
    
    except Exception as e:
        logger.error(f"[API] Error getting simulation status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders/pending")
async def get_pending_simulation_orders():
    """
    Get all pending simulation orders.
    
    Returns list of pending fake orders with full details.
    """
    try:
        from app.simulation.fake_order_tracker import get_fake_order_tracker
        from app.api.market_data_routes import market_data_cache
        
        tracker = get_fake_order_tracker()
        pending_orders = tracker.get_pending_orders()
        
        # Enrich with current bid/ask for each symbol
        orders_data = []
        for order in pending_orders:
            order_dict = order.to_dict()
            
            # Add current market data
            market_data = market_data_cache.get(order.symbol, {})
            order_dict['current_bid'] = market_data.get('bid')
            order_dict['current_ask'] = market_data.get('ask')
            order_dict['current_last'] = market_data.get('last')
            
            orders_data.append(order_dict)
        
        return {
            "success": True,
            "count": len(orders_data),
            "orders": orders_data
        }
    
    except Exception as e:
        logger.error(f"[API] Error getting pending orders: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders/filled")
async def get_filled_simulation_orders():
    """
    Get all filled simulation orders.
    
    Returns list of filled fake orders with fill details.
    """
    try:
        from app.simulation.fake_order_tracker import get_fake_order_tracker
        
        tracker = get_fake_order_tracker()
        filled_orders = tracker.get_filled_orders()
        
        # Convert to dict for JSON
        orders_data = [order.to_dict() for order in filled_orders]
        
        return {
            "success": True,
            "count": len(orders_data),
            "orders": orders_data
        }
    
    except Exception as e:
        logger.error(f"[API] Error getting filled orders: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/simulate-fills")
async def simulate_fills(request: FillRequest):
    """
    Simulate order fills ("10 min later" button).
    
    1. Shuffles Market Data (Price Jitter)
    2. Publishes Fake Ticks to Redis (Tricks Engine into seeing movement)
    3. Randomly fills a percentage of pending orders
    """
    try:
        controller = get_simulation_controller()
        
        # Safety check
        if not controller.is_simulation_mode():
            raise HTTPException(
                status_code=400,
                detail="Not in simulation mode (enable LIFELESS + Simulation)"
            )
            
        # 1. SHUFFLE PRICES (Simulate Market Movement)
        from app.core.data_fabric import DataFabric
        from app.core.event_bus import EventBus
        
        fabric = DataFabric()
        shuffled_count = fabric.shuffle_lifeless_data()
        logger.info(f"[API] Shuffled {shuffled_count} symbols for simulation")
        
        # 2. BROADCAST FAKE TICKS (So Engine sees the movement)
        # Iterate over shuffled data and publish to "ticks" channel
        # This tricks the Engine (which listens to Redis) into processing "New Data"
        if shuffled_count > 0:
            symbols = fabric.get_all_live_symbols()
            published_count = 0
            
            for symbol in symbols:
                data = fabric.get_live(symbol)
                if not data: continue
                
                # Create Normalized Tick (Hammer Format)
                tick = {
                    "symbol": symbol,
                    "last": str(data.get('last', 0)),
                    "bid": str(data.get('bid', 0)),
                    "ask": str(data.get('ask', 0)),
                    "volume": str(data.get('volume', 0)),
                    "ts": str(int(data.get('timestamp', 0) * 1000)),
                    "exch": "SIM", # Mark as Simulation Exchange
                    "simulation": True # Explicit Flag
                }
                
                # Publish to Redis "ticks" channel (Engine listens to this)
                EventBus.publish("ticks", tick)
                published_count += 1
                
            logger.info(f"📡 Broadcasted {published_count} fake ticks to Engine")

        # 3. SIMULATE FILLS
        simulator = get_fill_simulator()
        filled_orders = simulator.simulate_fills(
            fill_percentage=request.fill_percentage,
            min_fills=request.min_fills,
            max_slippage=request.max_slippage
        )
        
        logger.info(f"[API] Simulated {len(filled_orders)} fills")
        
        return {
            "filled_count": len(filled_orders),
            "shuffled_count": shuffled_count,
            "filled_orders": [order.to_dict() for order in filled_orders],
            "message": f"✅ Market Moved & {len(filled_orders)} Orders Filled"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Error simulating fills: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders")
async def get_fake_orders(
    status: Optional[str] = Query(None, description="Filter by status: PENDING, FILLED, etc."),
    symbol: Optional[str] = Query(None, description="Filter by symbol")
):
    """Get fake orders"""
    try:
        tracker = get_fake_order_tracker()
        
        # Apply filters
        if status == 'PENDING':
            orders = tracker.get_pending_orders()
        elif status == 'FILLED':
            orders = tracker.get_filled_orders()
        elif symbol:
            orders = tracker.get_orders_by_symbol(symbol)
        else:
            orders = list(tracker.orders.values())
        
        return {
            "count": len(orders),
            "orders": [order.to_dict() for order in orders]
        }
    
    except Exception as e:
        logger.error(f"[API] Error getting fake orders: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
async def reset_simulation():
    """Reset simulation (clear all fake orders)"""
    try:
        controller = get_simulation_controller()
        
        # Safety: Only in simulation mode
        if not controller.is_simulation_mode():
            raise HTTPException(
                status_code=400,
                detail="Not in simulation mode"
            )
        
        reset_fake_order_tracker()
        
        logger.info("[API] Simulation reset - all fake orders cleared")
        
        return {
            "status": "reset",
            "message": "All fake orders cleared"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Error resetting simulation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders/{order_id}")
async def get_fake_order(order_id: str):
    """Get specific fake order by ID"""
    try:
        tracker = get_fake_order_tracker()
        order = tracker.get_order(order_id)
        
        if not order:
            raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
        
        return order.to_dict()
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] Error getting fake order: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
