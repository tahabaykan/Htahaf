"""load_test/fake_tick_publisher.py

Yüksek hacimli tick publisher - load test için.

Bu script yüksek sayıda symbol ve yüksek tick rate ile
sistem yük testi yapmak için kullanılır.

Kullanım:
    python load_test/fake_tick_publisher.py --symbols 500 --rate 10

Environment Variables:
    REDIS_URL: Redis connection URL
    N_SYMBOLS: Symbol sayısı (default: 500)
    TICK_RATE: Saniyede tick sayısı (default: 10)
    DURATION: Test süresi (saniye, default: 60)
"""

import asyncio
import os
import time
import random
import signal
import sys
import argparse
from typing import Dict, List
from collections import defaultdict

from aioredis import from_url
from utils.logging_config import setup_logging, get_logger

# Configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
STREAM = 'ticks'
SYMBOL_PREFIX = os.getenv('SYMBOL_PREFIX', 'SYM')

# Logging
setup_logging(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = get_logger(__name__)


class LoadTestPublisher:
    """Yüksek hacimli tick publisher"""
    
    def __init__(self, n_symbols: int = 500, tick_rate: float = 10.0):
        """
        Args:
            n_symbols: Symbol sayısı
            tick_rate: Saniyede tick sayısı (tüm symbol'ler için toplam)
        """
        self.n_symbols = n_symbols
        self.tick_rate = tick_rate
        self.symbols = [f"{SYMBOL_PREFIX}{i}" for i in range(n_symbols)]
        
        # Base prices (her symbol için)
        self.base_prices = {
            sym: 100 + random.random() * 50 
            for sym in self.symbols
        }
        
        # Stats
        self.tick_count = 0
        self.start_time = None
        self.running = False
        
        # Batch için
        self.batch_size = max(1, int(tick_rate / 10))  # Her batch'te ~10 tick
        
    async def publish_batch(self, redis_client, symbols: List[str], timestamp: float):
        """Birden fazla tick'i batch olarak yayınla"""
        # Pipeline kullan (daha hızlı)
        pipe = redis_client.pipeline()
        
        for sym in symbols:
            # Random walk price
            change = (random.random() - 0.5) * 2  # -1 to +1
            self.base_prices[sym] = max(1.0, self.base_prices[sym] + change)
            
            tick = {
                'symbol': sym,
                'last': f"{self.base_prices[sym]:.4f}",
                'bid': f"{self.base_prices[sym] - 0.01:.4f}",
                'ask': f"{self.base_prices[sym] + 0.01:.4f}",
                'ts': str(timestamp),
                'volume': str(random.randint(100, 10000))
            }
            
            pipe.xadd(STREAM, tick)
        
        # Execute pipeline
        await pipe.execute()
        self.tick_count += len(symbols)
    
    async def publish_loop(self, duration: int = 60):
        """
        Publish loop.
        
        Args:
            duration: Test süresi (saniye)
        """
        r = await from_url(REDIS_URL)
        
        self.running = True
        self.start_time = time.time()
        end_time = self.start_time + duration
        
        # Tick interval hesapla
        tick_interval = 1.0 / self.tick_rate if self.tick_rate > 0 else 0.1
        
        logger.info(
            f"Load test başlatılıyor: {self.n_symbols} symbols, "
            f"{self.tick_rate} ticks/s, {duration}s süre"
        )
        
        try:
            while self.running and time.time() < end_time:
                loop_start = time.time()
                
                # Batch'te yayınla
                batch_symbols = random.sample(
                    self.symbols, 
                    min(self.batch_size, len(self.symbols))
                )
                
                await self.publish_batch(r, batch_symbols, time.time())
                
                # Rate limiting
                elapsed = time.time() - loop_start
                sleep_time = max(0, tick_interval - elapsed)
                if sleep_time > 0:
                    await asyncio.sleep(sleep_time)
                
                # Periodic stats
                if self.tick_count % (self.n_symbols * 5) == 0:
                    elapsed_total = time.time() - self.start_time
                    actual_rate = self.tick_count / elapsed_total if elapsed_total > 0 else 0
                    logger.info(
                        f"Published {self.tick_count} ticks | "
                        f"Rate: {actual_rate:.1f} ticks/s | "
                        f"Elapsed: {elapsed_total:.1f}s"
                    )
        
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.error(f"Error in publish loop: {e}", exc_info=True)
        finally:
            await r.close()
            
            # Final stats
            total_time = time.time() - self.start_time if self.start_time else 0
            avg_rate = self.tick_count / total_time if total_time > 0 else 0
            
            logger.info("=== Load Test Sonuçları ===")
            logger.info(f"Total ticks: {self.tick_count}")
            logger.info(f"Total time: {total_time:.1f}s")
            logger.info(f"Average rate: {avg_rate:.1f} ticks/s")
            logger.info(f"Target rate: {self.tick_rate} ticks/s")
            logger.info(f"Symbols: {self.n_symbols}")


async def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Load test tick publisher')
    parser.add_argument('--symbols', type=int, default=500, help='Symbol sayısı')
    parser.add_argument('--rate', type=float, default=10.0, help='Tick rate (ticks/s)')
    parser.add_argument('--duration', type=int, default=60, help='Test süresi (saniye)')
    
    args = parser.parse_args()
    
    publisher = LoadTestPublisher(n_symbols=args.symbols, tick_rate=args.rate)
    
    # Signal handler
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        publisher.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await publisher.publish_loop(duration=args.duration)
    except KeyboardInterrupt:
        logger.info("Shutdown complete")


if __name__ == '__main__':
    asyncio.run(main())








