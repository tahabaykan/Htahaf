"""
QeBench Data Worker

Background task that keeps benchmark price cache hot:
- Refreshes DOS Group averages for all active positions every 10s
- Monitors account mode changes

NOTE: Fill tracking is now handled automatically by daily_fills_store._update_qebench()
      This worker only handles proactive cache warming.
"""
import asyncio
from loguru import logger
from datetime import datetime

from app.qebench.benchmark import get_benchmark_fetcher


class QeBenchDataWorker:
    def __init__(self):
        self.bench_fetcher = get_benchmark_fetcher()
        self.current_account = None
    
    async def run(self):
        """Main worker loop - benchmark cache refresh only"""
        logger.info("[QeBench Worker] Starting benchmark cache warmer...")
        
        while True:
            try:
                await self.update_benchmarks()
                await asyncio.sleep(10)  # Refresh every 10 seconds
            except Exception as e:
                logger.error(f"[QeBench Worker] Error: {e}")
                await asyncio.sleep(10)

    async def update_benchmarks(self):
        """
        Proactively calculate and cache benchmarks for all active positions.
        This offloads the calculation from the API request thread.
        """
        try:
            # Get active account
            from app.psfalgo.account_mode import get_account_mode_manager
            mode_mgr = get_account_mode_manager()
            account_id = mode_mgr.current_mode.value
            
            # Track account change
            if account_id != self.current_account:
                logger.info(f"[QeBench Worker] Account changed: {self.current_account} → {account_id}")
                self.current_account = account_id
            
            # Get positions directly from API
            from app.psfalgo.position_snapshot_api import get_position_snapshot_api
            pos_api = get_position_snapshot_api()
            
            # Fetch positions (this is async)
            current_positions = await pos_api.get_position_snapshot(account_id=account_id)
            
            count = 0
            for pos in current_positions:
                symbol = getattr(pos, 'symbol', None)
                if symbol:
                    # This call will trigger calculation and Redis caching
                    self.bench_fetcher.get_current_benchmark_price(symbol)
                    count += 1
            
            if count > 0:
                logger.debug(f"[QeBench Worker] Refreshed benchmarks for {count} positions ({account_id})")
                
        except Exception as e:
            logger.warning(f"[QeBench Worker] Update benchmarks error: {e}")
