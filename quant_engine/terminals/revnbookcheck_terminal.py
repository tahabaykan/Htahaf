"""
RevnBookCheck Terminal - REV Order Recovery Monitoring

Bu terminal RevnBookCheckTerminal kullanır. Akış:
1) Hangi hesap modu açık tanımlanır (Redis / psfalgo:account_mode)
2) O hesap açılır, pozisyonlar çekilebilir hale getirilir
3) Ancak ondan sonra Health kontrolü (BEFDAY / Current / Potential) yapılır

Ayrıca placement_callback sayesinde hesaplanan REV emirleri gerçekten gönderilir.
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.terminals.revnbookcheck import RevnBookCheckTerminal
from app.market_data.static_data_store import initialize_static_store
from app.psfalgo.position_snapshot_api import initialize_position_snapshot_api
from app.core.logger import logger


async def main():
    """RevnBookCheckTerminal ile tek akış: hesap modu → hesap aç → health check."""
    logger.info("=" * 80)
    logger.info("RevnBookCheck Terminal - Starting")
    logger.info("=" * 80)

    try:
        static_store = initialize_static_store()
        static_store.load_csv()
        initialize_position_snapshot_api(static_store=static_store)

        # Initialize ExposureCalculator (prevents "not initialized" errors)
        from app.psfalgo.exposure_calculator import initialize_exposure_calculator
        initialize_exposure_calculator()
        logger.info("[RevnBookCheck] ExposureCalculator initialized")

        # Initialize ExecutionRouter (Frontlama needs it for readiness checks)
        try:
            from app.execution.execution_router import get_execution_router
            router = get_execution_router()
            if router:
                logger.info("[RevnBookCheck] ExecutionRouter initialized")
        except Exception as e:
            logger.warning(f"[RevnBookCheck] ExecutionRouter init skipped: {e}")

        terminal = RevnBookCheckTerminal()
        await terminal.start()
    except KeyboardInterrupt:
        logger.info("[RevnBookCheck] Stopped by user")
    except Exception as e:
        logger.error(f"[RevnBookCheck] Fatal error: {e}", exc_info=True)
    finally:
        logger.info("[RevnBookCheck] Terminal shutdown")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTerminal stopped.")
