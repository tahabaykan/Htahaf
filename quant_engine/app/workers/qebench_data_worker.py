"""
QeBench Data Worker

Tracks position fills and maintains QeBench CSV:
- Monitors current positions from trading system
- Detects new positions (qty increases)
- Records fills with bench@fill price
- Updates weighted averages
"""
import asyncio
from loguru import logger
from datetime import datetime

from app.qebench import get_qebench_csv
from app.qebench.calculator import merge_position_with_fill
from app.qebench.benchmark import get_benchmark_fetcher


class QeBenchDataWorker:
    def __init__(self):
        self.bench_fetcher = get_benchmark_fetcher()
        self.last_positions = {}  # symbol -> qty
        self.current_account = None
        self.csv_mgr = None
    
    def _get_active_csv(self):
        """Get CSV manager for currently active account"""
        from app.psfalgo.account_mode import get_account_mode_manager
        
        mode_mgr = get_account_mode_manager()
        active_account = mode_mgr.current_mode.value
        
        # If account changed, switch CSV
        if active_account != self.current_account:
            logger.info(f"[QeBench Worker] Account changed: {self.current_account} → {active_account}")
            self.current_account = active_account
            self.csv_mgr = get_qebench_csv(account=active_account)
            self.last_positions = {}  # Reset tracking
        
        return self.csv_mgr
    
    async def run(self):
        """Main worker loop"""
        logger.info("[QeBench Worker] Starting...")
        
        while True:
            try:
                await self.check_for_fills()
                await asyncio.sleep(10)  # Check every 10 seconds
            except Exception as e:
                logger.error(f"[QeBench Worker] Error: {e}")
                await asyncio.sleep(10)
    
    async def check_for_fills(self):
        """Check for new fills by comparing positions"""
        try:
            # Get CSV for active account
            csv_mgr = self._get_active_csv()
            
            # Get current positions from trading system
            from app.api.trading_routes import get_positions_snapshot
            positions_response = await get_positions_snapshot()
            current_positions = positions_response.get('positions', [])
            
            for pos in current_positions:
                symbol = pos.get('symbol')
                current_qty = pos.get('qty', 0)
                avg_cost = pos.get('avg_cost', 0.0)
                
                if not symbol or current_qty == 0:
                    continue
                
                # Check if this is a new position or qty increased
                last_qty = self.last_positions.get(symbol, 0)
                
                if current_qty != last_qty:
                    # Position changed!
                    qty_change = abs(current_qty - last_qty)
                    
                    # Get benchmark price NOW
                    bench_price = self.bench_fetcher.get_current_benchmark_price(symbol)
                    
                    if bench_price is None:
                        logger.warning(f"[QeBench] No bench price for {symbol}, skipping")
                        self.last_positions[symbol] = current_qty
                        continue
                    
                    # Get existing QB position
                    qb_pos = csv_mgr.get_position(symbol)
                    
                    if qb_pos is None:
                        # New position - first fill
                        logger.info(f"[QeBench] NEW POSITION: {symbol} {current_qty}@{avg_cost:.2f} bench@{bench_price:.2f}")
                        
                        csv_mgr.update_position(
                            symbol=symbol,
                            total_qty=current_qty,
                            weighted_avg_cost=avg_cost,
                            weighted_bench_fill=bench_price
                        )
                        
                        csv_mgr.add_fill(
                            symbol=symbol,
                            qty=current_qty,
                            fill_price=avg_cost,
                            bench_price=bench_price,
                            source="AUTO"
                        )
                    else:
                        # Position increased - new fill
                        logger.info(f"[QeBench] FILL DETECTED: {symbol} +{qty_change} @ bench{bench_price:.2f}")
                        
                        # Merge with existing
                        updated = merge_position_with_fill(
                            existing_position=qb_pos,
                            fill_qty=qty_change,
                            fill_price=avg_cost,
                            bench_price_at_fill=bench_price
                        )
                        
                        csv_mgr.update_position(
                            symbol=symbol,
                            total_qty=updated['total_qty'],
                            weighted_avg_cost=updated['weighted_avg_cost'],
                            weighted_bench_fill=updated['weighted_bench_fill']
                        )
                        
                        csv_mgr.add_fill(
                            symbol=symbol,
                            qty=qty_change,
                            fill_price=avg_cost,
                            bench_price=bench_price,
                            source="AUTO"
                        )
                    
                    # Update last known qty
                    self.last_positions[symbol] = current_qty
        
        except Exception as e:
            logger.error(f"[QeBench Worker] Check fills error: {e}")
