"""
Run QeBench Data Worker Terminal

Tracks fills and maintains QeBench CSV data.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from loguru import logger
from app.workers.qebench_data_worker import QeBenchDataWorker


async def main():
    logger.info("=" * 60)
    logger.info("🎯 QeBench Data Worker Terminal")
    logger.info("=" * 60)
    
    worker = QeBenchDataWorker()
    
    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("\n⏹️ Shutting down QeBench worker...")
    except Exception as e:
        logger.error(f"❌ Worker error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
