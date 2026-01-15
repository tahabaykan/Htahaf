"""
QeBenchData Worker
Dedicated process for logging trade fills and calculating benchmarks.
"""
import os
import sys
import time
import signal
import threading
from pathlib import Path
from dotenv import load_dotenv

# Force load .env from root before anything else
env_path = Path(r"c:\StockTracker\.env")
if env_path.exists():
    load_dotenv(env_path)

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.logger import logger
from app.analysis.qebenchdata import get_bench_logger
# from app.api.trading_routes import initialize_trading_context # Removed - does not exist

# Flags for shutdown
RUNNING = True

def signal_handler(sig, frame):
    global RUNNING
    logger.info("Shutdown signal received...")
    RUNNING = False

def run_worker():
    global RUNNING
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("==================================================")
    logger.info("   QeBenchData Worker - Starting")
    logger.info("   - Fill Logging & Benchmark Calculation")
    logger.info("   - Hammer & IBKR Integration")
    logger.info("==================================================")
    
    # 1. Initialize Trading Context
    from app.api.market_data_routes import initialize_market_data_services
    from app.psfalgo.account_mode import initialize_account_mode_manager
    
    # Initialize Account Mode (defaults to Hammer Pro, mimics main.py)
    initialize_account_mode_manager(initial_mode="HAMMER_PRO")
    
    # Initialize Market Data (Loads CSV for StaticDataStore - Critical for Peer Groups)
    initialize_market_data_services()
    
    # 2. Initialize Hammer Client (Observer for Fills in HAMMPRO mode)
    # We create a specific client for this worker
    from app.live.hammer_client import HammerClient
    # Hardcoded password per user request to bypass env var issues
    hammer_client = HammerClient(password="Nl201090.")
    if hammer_client.connect():
        logger.info("✅ Hammer Client Connected")
        # Start trading account
        # Note: HammerClient.connect() doesn't auto-start account unless configured?
        # HammerClient implementation in this codebase has auth and startDataStreamer in _on_open/connect flow
        # We need to ensure we subscribe to 'transactions'
        pass 
    else:
        logger.warning("⚠️ Hammer Client could not connect (Functionality Limited)")

    # 3. Initialize IBKR Connector (For IBKR Fills)
    from app.psfalgo.ibkr_connector import initialize_ibkr_connectors, get_ibkr_connector
    initialize_ibkr_connectors()
    
    # Note: IBKR Connectors need to be CONNECTED.
    # The default initialize just creates objects.
    # We should trigger auto-connect if mode is IBKR.
    # Or rely on AccountModeManager?
    
    # 4. Initialize QeBenchDataLogger
    bench_logger = get_bench_logger()
    logger.info("✅ QeBenchDataLogger Initialized")
    
    # Hook Logger to Hammer
    # We need to add logger's handler to hammer_client observers
    # QeBenchDataLogger doesn't expose a 'on_hammer_message' public method directly tailored for raw msgs yet?
    # Actually `log_fill` is the entry point.
    # We need an adapter.
    
    def on_hammer_message(msg):
        cmd = msg.get('cmd')
        if cmd == 'transactionsUpdate':
            # Parse and log
            res = msg.get('result', {})
            trans = res.get('transactions', [])
            for t in trans:
                # Map Hammer transaction to log_fill
                # ... extraction logic ...
                # For now, placeholder or needs implementation in this script
                pass
                
    hammer_client.add_observer(on_hammer_message)
    
    logger.info("🚀 Worker Running... Waiting for fills.")
    
    while RUNNING:
        time.sleep(1)

    logger.info("Worker Shutdown Complete.")

if __name__ == "__main__":
    run_worker()
