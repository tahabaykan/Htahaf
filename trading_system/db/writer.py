"""db/writer.py

Exec stream'inden gelen verileri Postgres'e yazan basit örnek.

Bu modül:
    - Redis execs stream'ini tüketir
    - Execution verilerini Postgres/TimescaleDB'ye yazar
    - Batch insert için optimizasyon

Kullanım:
    python db/writer.py

Environment Variables:
    REDIS_URL: Redis connection URL (default: redis://localhost:6379)
    PG_DSN: Postgres connection string (default: postgresql://user:pass@localhost:5432/trades)
    BATCH_SIZE: Batch insert size (default: 10)
"""

import asyncio
import os
import time

from aioredis import from_url
import asyncpg

from utils.logging_config import setup_logging, get_logger

# Configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
EXEC_STREAM = 'execs'
PG_DSN = os.getenv('PG_DSN', 'postgresql://user:pass@localhost:5432/trades')
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '10'))

# Logging
setup_logging(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = get_logger(__name__)


async def ensure_table(pg_conn):
    """
    execs tablosunu oluştur (yoksa).
    
    Args:
        pg_conn: asyncpg connection
    """
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS execs (
        id SERIAL PRIMARY KEY,
        symbol VARCHAR(50),
        order_id VARCHAR(50),
        status VARCHAR(50),
        price DECIMAL(20, 4),
        quantity DECIMAL(20, 4),
        filled DECIMAL(20, 4),
        remaining DECIMAL(20, 4),
        avg_fill_price DECIMAL(20, 4),
        last_fill_price DECIMAL(20, 4),
        ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        meta JSONB
    );
    
    CREATE INDEX IF NOT EXISTS idx_execs_symbol ON execs(symbol);
    CREATE INDEX IF NOT EXISTS idx_execs_ts ON execs(ts);
    """
    
    await pg_conn.execute(create_table_sql)
    logger.info("Table 'execs' ensured")


async def write_execution(pg_conn, exec_data: dict):
    """
    Tek bir execution'ı DB'ye yaz.
    
    Args:
        pg_conn: asyncpg connection
        exec_data: Execution data dict
    """
    try:
        await pg_conn.execute(
            """
            INSERT INTO execs (symbol, order_id, status, price, quantity, filled, remaining, 
                            avg_fill_price, last_fill_price, meta)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            exec_data.get('symbol'),
            exec_data.get('order_id'),
            exec_data.get('status'),
            float(exec_data.get('price', 0) or 0),
            float(exec_data.get('quantity', 0) or 0),
            float(exec_data.get('filled', 0) or 0),
            float(exec_data.get('remaining', 0) or 0),
            float(exec_data.get('avg_fill_price', 0) or 0),
            float(exec_data.get('last_fill_price', 0) or 0),
            str(exec_data)  # meta as JSONB
        )
    except Exception as e:
        logger.error(f"Error writing execution: {e}")


async def main():
    """Main entry point"""
    r = await from_url(REDIS_URL)
    pg = await asyncpg.connect(PG_DSN)
    
    # Table oluştur
    await ensure_table(pg)
    
    last_id = '0-0'
    write_count = 0
    batch = []
    
    logger.info("DB writer started")
    
    try:
        while True:
            try:
                # Stream'den oku
                msgs = await r.xread({EXEC_STREAM: last_id}, count=BATCH_SIZE, block=2000)
                
                if not msgs:
                    # Batch'i yaz (bekleyen varsa)
                    if batch:
                        for exec_data in batch:
                            await write_execution(pg, exec_data)
                        write_count += len(batch)
                        batch = []
                        logger.info(f"Written {write_count} executions to DB")
                    await asyncio.sleep(0.1)
                    continue
                
                # Decode messages
                for stream, items in msgs:
                    for msg_id, data in items:
                        last_id = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
                        
                        # Decode data
                        exec_data = {}
                        for k, v in data.items():
                            key = k.decode() if isinstance(k, bytes) else k
                            val = v.decode() if isinstance(v, bytes) else v
                            exec_data[key] = val
                        
                        batch.append(exec_data)
                
                # Batch yaz
                if len(batch) >= BATCH_SIZE:
                    for exec_data in batch:
                        await write_execution(pg, exec_data)
                    write_count += len(batch)
                    logger.info(f"Written {write_count} executions to DB (batch: {len(batch)})")
                    batch = []
            
            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                await asyncio.sleep(1)
    
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    finally:
        # Kalan batch'i yaz
        if batch:
            for exec_data in batch:
                await write_execution(pg, exec_data)
            write_count += len(batch)
            logger.info(f"Final batch written. Total: {write_count}")
        
        await r.close()
        await pg.close()
        logger.info("DB writer stopped")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown complete")








