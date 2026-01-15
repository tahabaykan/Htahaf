"""collector/publish_tick.py

Basit tick publisher demo. Gerçek market data yerine rastgele tick üretir.

Amaç: Redis `ticks` stream'ine xadd örneği göstermek.

Kullanım (dev):
    python collector/publish_tick.py

Varsayılan Redis URL: redis://localhost:6379

Environment Variables:
    REDIS_URL: Redis connection URL
    N_SYMBOLS: Üretilecek symbol sayısı (default: 50)
    DELAY: Tick arası gecikme (saniye, default: 0.1)
    SYMBOL_PREFIX: Symbol prefix (default: SYM)
"""

import asyncio
import os
import time
import random
import signal
import sys

from aioredis import from_url
from utils.logging_config import setup_logging, get_logger

# Configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
STREAM = 'ticks'
N_SYMBOLS = int(os.getenv('N_SYMBOLS', '50'))
DELAY = float(os.getenv('DELAY', '0.1'))
SYMBOL_PREFIX = os.getenv('SYMBOL_PREFIX', 'SYM')

# Logging
setup_logging(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = get_logger(__name__)


async def publish_loop(n_symbols: int = N_SYMBOLS, delay: float = DELAY):
    """
    Tick publish loop.
    
    Args:
        n_symbols: Symbol sayısı
        delay: Tick arası gecikme (saniye)
    """
    r = await from_url(REDIS_URL)
    syms = [f"{SYMBOL_PREFIX}{i}" for i in range(n_symbols)]
    
    # Base prices (her symbol için)
    base_prices = {sym: 100 + random.random() * 50 for sym in syms}
    
    running = True
    
    def signal_handler(sig, frame):
        nonlocal running
        logger.info("Shutdown signal received")
        running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    tick_count = 0
    
    try:
        logger.info(f"Starting tick publisher: {n_symbols} symbols, {delay}s delay")
        
        while running:
            ts = time.time()
            
            for sym in syms:
                # Random walk price
                change = (random.random() - 0.5) * 2  # -1 to +1
                base_prices[sym] = max(1.0, base_prices[sym] + change)
                
                # Tick data
                tick = {
                    'symbol': sym,
                    'last': f"{base_prices[sym]:.4f}",
                    'bid': f"{base_prices[sym] - 0.01:.4f}",
                    'ask': f"{base_prices[sym] + 0.01:.4f}",
                    'ts': str(ts),
                    'volume': str(random.randint(100, 10000))
                }
                
                await r.xadd(STREAM, tick)
                tick_count += 1
            
            # Periodic log
            if tick_count % (n_symbols * 10) == 0:
                logger.info(f"Published {tick_count} ticks")
            
            await asyncio.sleep(delay)
    
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Error in publish loop: {e}", exc_info=True)
    finally:
        await r.close()
        logger.info(f"Publisher stopped. Total ticks: {tick_count}")


if __name__ == '__main__':
    try:
        asyncio.run(publish_loop())
    except KeyboardInterrupt:
        logger.info("Shutdown complete")








