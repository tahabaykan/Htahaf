import os
import sys
import logging
import threading
import time

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.ui.janall_control_panel import JanallControlPanel
from app.ibkr.ib_native_connector import IBNativeConnector
from app.live.hammer_client import HammerClient

# Setup basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("JanallLauncher")

class SimpleMarketDataAdapter:
    def __init__(self, hammer):
        self.hammer = hammer
        
    def get_market_data(self, ticker):
        """
        Adapts HammerClient.get_market_data to the format expected by JanallBulkOrderManager.
        Expects: {'bid': float, 'ask': float, 'last': float}
        """
        # HammerClient typically stores data in a cache or fetches it
        # Assuming hammer.get_snapshot/get_market_data exists or we use internal cache
        # Inspecting HammerClient code previously: it has `market_data` dict.
        
        # Convert PREF IBKR (BFS PRE) to Hammer (BFS-E) if needed?
        # HammerClient usually handles mapping.
        
        # Try to get from Hammer cache
        if hasattr(self.hammer, 'market_data'):
            # Try variations of symbol
            syms = [ticker, ticker.replace(' PR', '-')]
            for s in syms:
                if s in self.hammer.market_data:
                    d = self.hammer.market_data[s]
                    return {
                        'bid': float(d.get('bid', 0)),
                        'ask': float(d.get('ask', 0)),
                        'last': float(d.get('last', 0) or d.get('price', 0))
                    }
        return {'bid': 0.0, 'ask': 0.0, 'last': 0.0}

def main():
    logger.info("Starting Janall Port UI...")
    
    # 1. Initialize IB Native
    logger.info("Connecting to IBKR Native (Port 4001)...")
    ib_client = IBNativeConnector(host='127.0.0.1', port=4001, client_id=888)
    ib_connected = ib_client.connect_client()
    
    if not ib_connected:
        logger.warning("Could not connect to IBKR Native! Falling back to Dummy Mode.")
        
    # 2. Initialize Hammer
    try:
        logger.info("Connecting to Hammer Pro...")
        hammer = HammerClient()
        hammer.connect()
    except Exception as e:
        logger.error(f"Hammer connection failed: {e}")
        hammer = None
        
    # 3. Market Data Adapter
    md_service = SimpleMarketDataAdapter(hammer)
    
    # 4. Launch UI
    app = JanallControlPanel(trading_client=ib_client, market_data_service=md_service)
    app.mainloop()

    # Cleanup
    if ib_client: ib_client.disconnect()
    if hammer: hammer.disconnect()

if __name__ == "__main__":
    main()
