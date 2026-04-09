"""
RevnBookCheck Terminal Worker

Auto REV Order Generator - monitors fills and creates TP/Reload orders.

Terminal 'r': RevnBookCheck
"""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from app.terminals.revnbookcheck import RevnBookCheckTerminal
from app.market_data.static_data_store import initialize_static_store
from app.psfalgo.position_snapshot_api import initialize_position_snapshot_api


async def main():
    """Main entry point"""
    print("=" * 80)
    print("🎯 Starting RevnBookCheck Terminal (Auto REV Order Generator)")
    print("=" * 80)
    print()
    print("Features:")
    print("  - Monitor fills in real-time")
    print("  - Generate REV orders (TP/Reload)")
    print("  - OrderBook analysis")
    print("  - Recovery on startup")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 80)
    print()
    
    try:
        # Initialize dependencies
        static_store = initialize_static_store()
        static_store.load_csv()
        initialize_position_snapshot_api(static_store=static_store)
        
        terminal = RevnBookCheckTerminal()
        await terminal.start()
    except KeyboardInterrupt:
        logger.info("[RevnBookCheck] Stopped by user")
    except Exception as e:
        logger.error(f"[RevnBookCheck] Fatal error: {e}", exc_info=True)


if __name__ == '__main__':
    asyncio.run(main())
