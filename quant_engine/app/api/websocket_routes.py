"""
WebSocket Routes for Real-time Market Data Updates
==================================================

Handles WebSocket connections for broadcasting market data updates to frontend.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Set, Optional, Dict, Any
import asyncio
import json

from app.core.logger import logger
from app.market_data.static_data_store import get_static_store as _get_static_store


router = APIRouter(prefix="/ws", tags=["WebSocket"])


class ConnectionManager:
    """Manages WebSocket connections and broadcasts"""
    
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._broadcast_task: Optional[asyncio.Task] = None
    
    async def connect(self, websocket: WebSocket):
        """Accept a new WebSocket connection"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"📡 WebSocket connected. Total connections: {len(self.active_connections)}")
        
        # Start broadcast loop if not already running
        if self._broadcast_task is None or self._broadcast_task.done():
            self._broadcast_task = asyncio.create_task(self._broadcast_loop())
    
    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        self.active_connections.discard(websocket)
        logger.info(f"📡 WebSocket disconnected. Total connections: {len(self.active_connections)}")
    
    async def broadcast(self, message: Dict[str, Any]):
        """Broadcast message to all connected clients"""
        if not self.active_connections:
            return
        
        try:
            # Safely serialize message (handle None, NaN, etc.)
            def safe_serialize(obj):
                """Safely serialize values for JSON"""
                if obj is None:
                    return None
                if isinstance(obj, float):
                    # Check for NaN or Infinity
                    if obj != obj or obj == float('inf') or obj == float('-inf'):
                        return None
                    return obj
                return obj
            
            # Clean message data before serialization
            clean_message = {
                "type": message.get("type"),
                "data": [
                    {k: safe_serialize(v) for k, v in item.items()}
                    for item in message.get("data", [])
                ]
            }
            
            message_json = json.dumps(clean_message, allow_nan=False)
            disconnected = set()
            
            for connection in self.active_connections:
                try:
                    await connection.send_text(message_json)
                except Exception as e:
                    logger.warning(f"Error broadcasting to client: {e}")
                    disconnected.add(connection)
            
            # Remove disconnected clients
            for conn in disconnected:
                self.disconnect(conn)
        except Exception as e:
            logger.error(f"Error in broadcast: {e}", exc_info=True)
    
    async def broadcast_symbol_update(self, symbol: str, data: Dict[str, Any]):
        """Broadcast update for a specific symbol"""
        await self.broadcast({
            "type": "market_data_update",
            "symbol": symbol,
            "data": data
        })
    
    async def broadcast_jfin_update(self, jfin_data: Dict[str, Any]):
        """Broadcast JFIN state update"""
        await self.broadcast({
            "type": "jfin_update",
            "data": jfin_data
        })
    
    async def broadcast_ticker_alert(self, alert_data: Dict[str, Any]):
        """Broadcast ticker alert (NEW_HIGH/NEW_LOW)"""
        await self.broadcast({
            "type": "ticker_alert",
            "alert": alert_data
        })
    
    async def _broadcast_loop(self):
        """Periodic broadcast loop for market data updates"""
        try:
            # Import functions once at the start
            from app.api.market_data_routes import get_dirty_symbols, clear_dirty_symbols, get_etf_market_data
            
            while len(self.active_connections) > 0:
                # Get dirty symbols and broadcast updates
                try:
                    dirty_symbols = get_dirty_symbols()
                    
                    # Import market_data_cache inside loop to get latest reference
                    from app.api.market_data_routes import ETF_TICKERS, get_etf_market_data
                    
                    # IMPORTANT: Preferred stocks are now sent IMMEDIATELY in update_market_data_cache()
                    # (event-driven, bypassing this loop). This loop only handles ETFs.
                    
                    # Get ETF symbols from dirty queue OR all ETFs if no dirty symbols (initial load)
                    etf_symbols = {s for s in dirty_symbols if s in ETF_TICKERS} if dirty_symbols else set()
                    
                    # If no dirty ETF symbols but we have active connections, broadcast all ETFs (initial load)
                    if not etf_symbols and len(self.active_connections) > 0:
                        # Check if we've broadcasted ETFs before (to avoid spamming on every loop)
                        if not hasattr(self, '_etf_initial_broadcast_done'):
                            self._etf_initial_broadcast_done = False
                        
                        if not self._etf_initial_broadcast_done:
                            # Initial load: broadcast all ETFs
                            etf_symbols = set(ETF_TICKERS)
                            self._etf_initial_broadcast_done = True
                            logger.info(f"📡 Initial ETF broadcast: {len(etf_symbols)} ETFs")
                    
                    # Broadcast ETF updates (for ETFStrip panel)
                    # ETFs can be batched since they're heavier (L1+L2+GRPAN)
                    if etf_symbols:
                        try:
                            etf_data = get_etf_market_data()
                            from app.api.market_data_routes import etf_prev_close
                            
                            etf_updates = []
                            for etf_symbol in etf_symbols:
                                etf_market_data = etf_data.get(etf_symbol)
                                # If no market data yet, at least send prev_close from CSV (for initial load)
                                if etf_market_data:
                                    etf_updates.append({
                                        'symbol': etf_symbol,
                                        'last': etf_market_data.get('last'),
                                        'prev_close': etf_market_data.get('prev_close'),
                                        'daily_change_percent': etf_market_data.get('daily_change_percent'),
                                        'daily_change_cents': etf_market_data.get('daily_change_cents'),
                                        'bid': etf_market_data.get('bid'),
                                        'ask': etf_market_data.get('ask')
                                    })
                                else:
                                    # No market data yet, but send prev_close from CSV (initial load)
                                    prev_close = etf_prev_close.get(etf_symbol)
                                    if prev_close:
                                        etf_updates.append({
                                            'symbol': etf_symbol,
                                            'last': None,
                                            'prev_close': prev_close,
                                            'daily_change_percent': None,
                                            'daily_change_cents': None,
                                            'bid': None,
                                            'ask': None
                                        })
                            
                            if etf_updates:
                                etf_broadcast_message = {
                                    "type": "etf_update",
                                    "data": etf_updates
                                }
                                await self.broadcast(etf_broadcast_message)
                                logger.info(f"📡 Broadcasted {len(etf_updates)} ETF updates")
                        except Exception as e:
                            logger.error(f"Error broadcasting ETF updates: {e}", exc_info=True)
                    
                    # Clear dirty symbols after broadcast (only ETFs remain, preferred are sent immediately)
                    try:
                        clear_dirty_symbols()
                    except Exception as e:
                        logger.debug(f"Error clearing dirty symbols: {e}")
                        
                except Exception as e:
                    logger.error(f"Error in broadcast loop iteration: {e}", exc_info=True)
                
                # Wait before next broadcast (3 seconds interval for ETF updates)
                # Preferred stocks are sent immediately (event-driven), so this loop only handles ETFs
                # ETFs are heavier (L1+L2+GRPAN) and don't need to update every second
                await asyncio.sleep(3.0)
        except asyncio.CancelledError:
            logger.info("📡 Broadcast loop cancelled")
        except Exception as e:
            logger.error(f"Fatal error in broadcast loop: {e}", exc_info=True)


# Global connection manager instance (initialized on module load)
connection_manager = ConnectionManager()


def get_connection_manager() -> Optional[ConnectionManager]:
    """Get global connection manager instance"""
    return connection_manager


# Export connection_manager for direct access (backward compatibility)
__all__ = ['router', 'ConnectionManager', 'connection_manager', 'get_connection_manager', 'get_static_store']


# Export get_static_store for backward compatibility
def get_static_store():
    """Get static data store (for backward compatibility)"""
    return _get_static_store()


@router.websocket("/market-data")
async def websocket_market_data(websocket: WebSocket):
    """WebSocket endpoint for real-time market data updates"""
    manager = get_connection_manager()
    if not manager:
        await websocket.close(code=1013, reason="Connection manager not available")
        return
    
    await manager.connect(websocket)
    
    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_text()
            # Echo back for ping/pong
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("📡 Client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        manager.disconnect(websocket)
