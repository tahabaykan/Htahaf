"""router/order_router.py

Orders stream'in (veya signals->risk->orders) çıktısını okuyup IB'ye ileten router.

Bu modül:
    - Redis orders stream'ini tüketir
    - Token bucket ile rate limiting yapar
    - ib_insync kullanarak IBKR'ye order gönderir
    - Execution sonuçlarını execs stream'ine yazar

NOT: ib_insync sync API olduğu için production'da router'ı ayrı process/thread içinde
çalıştırın veya run_in_executor kullanın.

Kullanım:
    python router/order_router.py

Environment Variables:
    REDIS_URL: Redis connection URL (default: redis://localhost:6379)
    IBKR_HOST: IBKR TWS/Gateway host (default: 127.0.0.1)
    IBKR_PORT: IBKR TWS/Gateway port (default: 4001)
    IBKR_CLIENT_ID: IBKR client ID (default: 1)
    RATE_LIMIT: Orders per second (default: 1.0)
    BUCKET_CAPACITY: Burst capacity (default: 5)
"""

import asyncio
import os
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional

from aioredis import from_url
from utils.token_bucket import TokenBucket
from utils.logging_config import setup_logging, get_logger

# ib_insync import (optional)
# Not: Mevcut projede ib_async kullanılıyor olabilir, burada ib_insync kullanıyoruz
try:
    from ib_insync import IB, Stock, MarketOrder, LimitOrder
    IB_AVAILABLE = True
except ImportError:
    # Fallback: ib_async deneyelim
    try:
        import ib_async
        from ib_async import IB
        from ib_async.contract import Stock
        from ib_async.order import MarketOrder, LimitOrder
        IB_AVAILABLE = True
    except ImportError:
        IB_AVAILABLE = False
        IB = None
        Stock = None
        MarketOrder = None
        LimitOrder = None

# Configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
ORDER_STREAM = 'orders'
EXEC_STREAM = 'execs'
ROUTER_GROUP = 'router_group'

# IBKR Configuration
IBKR_HOST = os.getenv('IBKR_HOST', '127.0.0.1')
IBKR_PORT = int(os.getenv('IBKR_PORT', '4001'))
IBKR_CLIENT_ID = int(os.getenv('IBKR_CLIENT_ID', '1'))

# Rate limiting
RATE_LIMIT = float(os.getenv('RATE_LIMIT', '1.0'))  # orders per second
BUCKET_CAPACITY = int(os.getenv('BUCKET_CAPACITY', '5'))

# Logging
setup_logging(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = get_logger(__name__)


class IBKRRouter:
    """IBKR order router with rate limiting"""
    
    def __init__(self):
        self.ib: Optional[IB] = None
        self.connected = False
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ibkr")
        self.token_bucket = TokenBucket(rate_per_second=RATE_LIMIT, capacity=BUCKET_CAPACITY)
        self.running = False
        self._lock = threading.Lock()
        
    def connect_ibkr(self) -> bool:
        """
        IBKR TWS/Gateway'e bağlan (sync, thread-safe).
        
        Returns:
            True if connected successfully
        """
        if not IB_AVAILABLE:
            logger.warning("ib_insync not available, using mock mode")
            return False
        
        try:
            with self._lock:
                if self.ib and self.connected:
                    return True
                
                logger.info(f"Connecting to IBKR: {IBKR_HOST}:{IBKR_PORT} (Client ID: {IBKR_CLIENT_ID})")
                self.ib = IB()
                self.ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID, timeout=15)
                
                if self.ib.isConnected():
                    self.connected = True
                    logger.info("✅ IBKR connected successfully")
                    
                    # Order status callbacks
                    self.ib.orderStatusEvent += self._on_order_status
                    self.ib.executionEvent += self._on_execution
                    
                    return True
                else:
                    logger.error("❌ IBKR connection failed")
                    return False
                    
        except Exception as e:
            logger.error(f"IBKR connection error: {e}")
            self.connected = False
            return False
    
    def disconnect_ibkr(self):
        """IBKR bağlantısını kapat"""
        try:
            with self._lock:
                if self.ib and self.connected:
                    self.ib.disconnect()
                    self.connected = False
                    logger.info("IBKR disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting IBKR: {e}")
    
    def _on_order_status(self, trade):
        """Order status callback"""
        try:
            status = trade.orderStatus.status
            order_id = trade.order.orderId
            symbol = trade.contract.symbol
            
            logger.info(f"Order status: {symbol} OrderID={order_id} Status={status}")
            
            # Execution bilgilerini execs stream'ine yaz (async)
            if status in ['Filled', 'PartiallyFilled']:
                asyncio.create_task(self._publish_execution(trade))
        except Exception as e:
            logger.error(f"Error in order status callback: {e}")
    
    def _on_execution(self, trade, fill):
        """Execution callback"""
        try:
            symbol = trade.contract.symbol
            exec_price = fill.execution.price
            exec_qty = fill.execution.shares
            
            logger.info(f"Execution: {symbol} {exec_qty} @ {exec_price}")
            
            # Execution bilgilerini execs stream'ine yaz
            asyncio.create_task(self._publish_execution(trade, fill))
        except Exception as e:
            logger.error(f"Error in execution callback: {e}")
    
    async def _publish_execution(self, trade, fill=None):
        """Execution bilgisini Redis execs stream'ine yaz"""
        try:
            r = await from_url(REDIS_URL)
            
            exec_data = {
                'symbol': trade.contract.symbol,
                'order_id': str(trade.order.orderId),
                'status': trade.orderStatus.status,
                'filled': str(trade.orderStatus.filled),
                'remaining': str(trade.orderStatus.remaining),
                'avg_fill_price': str(trade.orderStatus.avgFillPrice or '0'),
                'ts': str(time.time())
            }
            
            if fill:
                exec_data['last_fill_price'] = str(fill.execution.price)
                exec_data['last_fill_qty'] = str(fill.execution.shares)
            
            await r.xadd(EXEC_STREAM, exec_data)
            await r.close()
            
        except Exception as e:
            logger.error(f"Error publishing execution: {e}")
    
    def _send_order_sync(self, order_data: Dict[str, Any]) -> bool:
        """
        IBKR'ye order gönder (sync, thread-safe).
        
        Args:
            order_data: Order dict (symbol, action, price, quantity, order_type)
            
        Returns:
            True if order sent successfully
        """
        if not IB_AVAILABLE:
            # Mock mode
            logger.info(f"[MOCK] Order sent: {order_data}")
            return True
        
        try:
            with self._lock:
                if not self.connected or not self.ib:
                    logger.error("IBKR not connected")
                    return False
                
                symbol = order_data.get('symbol', '')
                action = order_data.get('action', 'BUY')
                quantity = float(order_data.get('quantity', 0))
                price = float(order_data.get('price', 0))
                order_type = order_data.get('order_type', 'LIMIT')
                
                if not symbol or quantity <= 0:
                    logger.error(f"Invalid order data: {order_data}")
                    return False
                
                # Contract oluştur
                contract = Stock(symbol, 'SMART', 'USD')
                
                # Order oluştur
                if order_type.upper() == 'LIMIT':
                    if price <= 0:
                        logger.error(f"Invalid price for LIMIT order: {price}")
                        return False
                    order = LimitOrder(action.upper(), quantity, price, tif='DAY')
                elif order_type.upper() == 'MARKET':
                    order = MarketOrder(action.upper(), quantity)
                else:
                    logger.error(f"Unsupported order type: {order_type}")
                    return False
                
                # Order gönder
                trade = self.ib.placeOrder(contract, order)
                logger.info(f"✅ Order sent: {symbol} {action} {quantity} @ {price} (OrderID: {trade.order.orderId})")
                
                return True
                
        except Exception as e:
            logger.error(f"Error sending order: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    async def send_order_async(self, order_data: Dict[str, Any]) -> bool:
        """
        IBKR'ye order gönder (async wrapper).
        
        Args:
            order_data: Order dict
            
        Returns:
            True if order sent successfully
        """
        # Thread pool'da çalıştır (ib_insync sync API)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self._send_order_sync,
            order_data
        )
    
    async def router_loop(self, consumer_name: str = 'router1'):
        """
        Router main loop - orders stream'ini tüketir, IBKR'ye gönderir.
        
        Args:
            consumer_name: Consumer adı
        """
        r = await from_url(REDIS_URL)
        
        # Consumer group oluştur
        try:
            await r.xgroup_create(ORDER_STREAM, ROUTER_GROUP, id='$', mkstream=True)
        except Exception:
            pass  # Group zaten var
        
        last_id = '0-0'
        self.running = True
        
        logger.info(f"Router started (consumer: {consumer_name})")
        
        try:
            while self.running:
                try:
                    # Stream'den oku
                    msgs = await r.xread({ORDER_STREAM: last_id}, count=5, block=2000)
                    
                    if not msgs:
                        await asyncio.sleep(0.05)
                        continue
                    
                    for stream, items in msgs:
                        for msg_id, data in items:
                            last_id = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
                            
                            # Decode data
                            order = {}
                            for k, v in data.items():
                                key = k.decode() if isinstance(k, bytes) else k
                                val = v.decode() if isinstance(v, bytes) else v
                                order[key] = val
                            
                            # Rate limiting
                            wait_time = self.token_bucket.wait_time()
                            if wait_time > 0:
                                logger.debug(f"Rate limit: waiting {wait_time:.2f}s")
                                await asyncio.sleep(wait_time)
                            
                            if not self.token_bucket.consume():
                                logger.warning("Rate limit: token bucket empty, skipping order")
                                continue
                            
                            # Order gönder
                            success = await self.send_order_async(order)
                            
                            if success:
                                logger.info(f"Order processed: {order.get('symbol')} {order.get('action')}")
                            else:
                                logger.error(f"Order failed: {order.get('symbol')} {order.get('action')}")
                            
                            # Execution bilgisi execs stream'ine yazılacak (callback'ten)
                            # Burada sadece order gönderildi bilgisini yazabiliriz
                            exec_data = {
                                'symbol': order.get('symbol', ''),
                                'order_id': 'pending',
                                'status': 'SENT',
                                'price': order.get('price', '0'),
                                'quantity': order.get('quantity', '0'),
                                'ts': str(time.time())
                            }
                            await r.xadd(EXEC_STREAM, exec_data)
                
                except Exception as e:
                    logger.error(f"Error in router loop: {e}")
                    await asyncio.sleep(1)
        
        finally:
            await r.close()
            self.disconnect_ibkr()
            self.executor.shutdown(wait=True)
            logger.info("Router stopped")


async def main():
    """Main entry point"""
    router = IBKRRouter()
    
    # Graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        router.running = False
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # IBKR'ye bağlan (async wrapper)
    loop = asyncio.get_event_loop()
    connected = await loop.run_in_executor(None, router.connect_ibkr)
    
    if not connected:
        logger.warning("IBKR not connected, continuing in mock mode")
    
    # Router loop'u başlat
    try:
        await router.router_loop()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        router.running = False
        router.disconnect_ibkr()


if __name__ == '__main__':
    asyncio.run(main())

