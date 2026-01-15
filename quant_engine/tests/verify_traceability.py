
import asyncio
import uuid
import logging
from datetime import datetime
from app.psfalgo.clean_log_store import initialize_clean_log_store, get_clean_log_store
from app.psfalgo.karbotu_engine import KarbotuEngine
from app.psfalgo.decision_models import DecisionRequest, ExposureSnapshot, SymbolMetrics, PositionSnapshot
from app.trading.trading_account_context import TradingAccountContext, TradingAccountMode

# Setup Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VERIFY_TRACE")

async def test_traceability():
    logger.info("Starting Traceability Verification")
    
    # 1. Initialize Stores
    initialize_clean_log_store()
    max_store = get_clean_log_store()
    
    # 2. Mock Context
    # We need to mock get_trading_context or ensure it works. 
    # Since we can't easily mock the global context without setting it, let's rely on default "UNKNOWN" or set it if possible.
    # Actually, the code handles exception for context.
    
    # 3. Create Correlation ID
    correlation_id = str(uuid.uuid4())
    logger.info(f"Generated Correlation ID: {correlation_id}")
    
    # 4. Prepare Mock Request
    req = DecisionRequest(
        snapshot_ts=datetime.now(),
        available_symbols=["AAPL"],
        metrics={
            "AAPL": SymbolMetrics(
                symbol="AAPL", 
                bid=150.0, 
                ask=150.1, 
                bid_buy_ucuzluk=0.01, # Example
                fbtot=1.2,
                gort=0.9
            )
        },
        positions=[
             PositionSnapshot(symbol="AAPL", qty=100, avg_price=140.0, current_price=150.0, unrealized_pnl=1000.0)
        ],
        exposure=ExposureSnapshot(pot_total=1000, pot_max=10000, long_lots=10, short_lots=0, net_exposure=10),
        correlation_id=correlation_id
    )
    
    # 5. Run Karbotu Engine (Mocked behavior)
    engine = KarbotuEngine()
    # Mocking eligibility to pass
    engine.is_eligible = lambda *args: (True, "Mock Eligible")
    
    # Run
    logger.info("Running Karbotu Engine...")
    try:
        response = await engine.karbotu_decision_engine(req)
        logger.info(f"Engine Response Correlation ID: {response.correlation_id}")
        
        if response.correlation_id != correlation_id:
            logger.error(f"FAILURE: Correlation ID mismatch. Expected {correlation_id}, got {response.correlation_id}")
        else:
            logger.info("SUCCESS: Correlation ID match in response.")
        
        logger.info(f"Decisions: {len(response.decisions)}")
        logger.info(f"Filtered: {len(response.filtered_out)}")
            
    except Exception as e:
        logger.error(f"Engine execution failed: {e}")

    # 6. Verify Logs
    logger.info("Verifying CleanLogs...")
    logs = max_store.get_logs("HAMPRO", correlation_id=correlation_id) 
    if not logs:
         logger.info("Retrying with UNKNOWN...")
         logs = max_store.get_logs("UNKNOWN", correlation_id=correlation_id)
    
    logger.info(f"Found {len(logs)} logs for correlation_id {correlation_id}")
    for log in logs:
        logger.info(f"LOG: [{log.severity}] {log.component}: {log.message} (TraceID: {log.correlation_id})")
        
    if len(logs) > 0:
        logger.info("SUCCESS: Logs found.")
    else:
        logger.info("WARNING: No logs found. Maybe context or default account ID issue? Check log store file.")

if __name__ == "__main__":
    asyncio.run(test_traceability())
