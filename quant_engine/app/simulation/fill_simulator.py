"""
Fill Simulator - Background worker for automatic order fills in simulation mode

Features:
- Runs every 10 seconds
- Checks pending orders against market data
- Auto-fills orders that meet criteria
- Only active when simulation mode is ON
"""
import asyncio
from typing import Dict
from loguru import logger

from app.simulation.fake_order_tracker import get_fake_order_tracker
from app.core.simulation_controller import get_simulation_controller


class FillSimulator:
    """
    Background worker that auto-fills simulation orders.
    
    Runs in a loop while simulation mode is active.
    Checks pending orders every 10 seconds and fills eligible ones.
    """
    
    def __init__(self):
        self.is_running = False
        self.task = None
        logger.info("[FillSimulator] Initialized")
    
    async def start(self):
        """Start the fill simulation loop"""
        if self.is_running:
            logger.warning("[FillSimulator] Already running")
            return
        
        self.is_running = True
        self.task = asyncio.create_task(self._fill_loop())
        logger.info("[FillSimulator] 🎭 Started auto-fill loop")
    
    async def stop(self):
        """Stop the fill simulation loop"""
        if not self.is_running:
            return
        
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        
        logger.info("[FillSimulator] Stopped auto-fill loop")
    
    async def _fill_loop(self):
        """Main fill loop - checks every 10 seconds"""
        logger.info("[FillSimulator] Fill loop started")
        
        while self.is_running:
            try:
                # Check if simulation mode is still active
                sim_controller = get_simulation_controller()
                if not sim_controller or not sim_controller.is_simulation_mode():
                    logger.debug("[FillSimulator] Simulation mode OFF - pausing auto-fill")
                    await asyncio.sleep(5)
                    continue
                
                # Get market data and tracker
                try:
                    from app.api.market_data_routes import market_data_cache
                    from app.core.data_fabric import get_data_fabric
                    
                    # In lifeless mode, use DataFabric data
                    # In live mode, use market_data_cache
                    fabric = get_data_fabric()
                    if fabric and fabric.is_lifeless_mode():
                        # Populate market_data_cache with fake data
                        # (This should already be done by RUNALL, but ensure it's up-to-date)
                        logger.debug("[FillSimulator] Using lifeless mode data from DataFabric")
                    
                    tracker = get_fake_order_tracker()
                    
                    # Try to fill eligible orders
                    filled_ids = tracker.auto_fill_eligible_orders(market_data_cache)
                    
                    if filled_ids:
                        logger.info(f"[FillSimulator] ✅ Auto-filled {len(filled_ids)} orders this cycle")
                    else:
                        logger.debug("[FillSimulator] No eligible orders to fill")
                
                except Exception as e:
                    logger.error(f"[FillSimulator] Error in fill cycle: {e}", exc_info=True)
                
                # Wait 10 seconds before next check
                await asyncio.sleep(10)
            
            except asyncio.CancelledError:
                logger.info("[FillSimulator] Fill loop cancelled")
                break
            except Exception as e:
                logger.error(f"[FillSimulator] Unexpected error in fill loop: {e}", exc_info=True)
                await asyncio.sleep(10)
        
        logger.info("[FillSimulator] Fill loop stopped")


# Global instance
_fill_simulator: FillSimulator = None


def get_fill_simulator() -> FillSimulator:
    """Get global fill simulator instance"""
    global _fill_simulator
    if _fill_simulator is None:
        _fill_simulator = FillSimulator()
    return _fill_simulator


async def start_fill_simulator():
    """Start the fill simulator"""
    simulator = get_fill_simulator()
    await simulator.start()


async def stop_fill_simulator():
    """Stop the fill simulator"""
    simulator = get_fill_simulator()
    await simulator.stop()
