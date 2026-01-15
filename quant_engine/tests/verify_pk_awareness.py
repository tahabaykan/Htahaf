
import asyncio
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.logger import logger
from app.psfalgo.decision_models import (
    DecisionRequest, 
    PositionSnapshot, 
    SymbolMetrics, 
    ExposureSnapshot
)
from app.psfalgo.reducemore_engine import reducemore_decision_engine

import logging
import sys

# Loguru configuration requires using logger.add
try:
    logger.remove()  # Remove default handler
except ValueError:
    pass

def custom_sink(message):
    sys.stdout.write(str(message))
    sys.stdout.flush()

logger.add(custom_sink, level="INFO", format="{message}")

async def verify_pk_awareness():
    """Verify Provider Awareness in REDUCEMORE"""
    print("\n[TEST] Starting Provider Awareness Verification...")
    
    # 1. Mock Positions (Mixed Hammer & IBKR)
    positions = [
        # HAMMER Positions
        PositionSnapshot(
            symbol="HMR1", qty=1000, avg_price=10.0, current_price=9.5, unrealized_pnl=-500,
            account_type="HAMMER_PRO", group="X", cgrup="Y"
        ),
        PositionSnapshot(
            symbol="HMR2", qty=2000, avg_price=20.0, current_price=19.0, unrealized_pnl=-2000,
            account_type="HAMMER_PRO", group="X", cgrup="Y"
        ),
        # IBKR GUN Positions
        PositionSnapshot(
            symbol="IBKR1", qty=500, avg_price=50.0, current_price=48.0, unrealized_pnl=-1000,
            account_type="IBKR_GUN", group="X", cgrup="Y"
        ),
        # IBKR PED Positions
        PositionSnapshot(
            symbol="IBKR2", qty=300, avg_price=100.0, current_price=95.0, unrealized_pnl=-1500,
            account_type="IBKR_PED", group="X", cgrup="Y"
        ),
        # Short Position (Hammer)
        PositionSnapshot(
            symbol="SHRT1", qty=-1000, avg_price=10.0, current_price=11.0, unrealized_pnl=-1000,
            account_type="HAMMER_PRO", group="X", cgrup="Y"
        )
    ]
    
    # 2. Mock Metrics
    metrics = {
        "HMR1": SymbolMetrics(symbol="HMR1", fbtot=0.8, ask_sell_pahalilik=-0.1, gort=-2.0),
        "HMR2": SymbolMetrics(symbol="HMR2", fbtot=0.8, ask_sell_pahalilik=-0.1, gort=-2.0),
        "IBKR1": SymbolMetrics(symbol="IBKR1", fbtot=0.8, ask_sell_pahalilik=-0.1, gort=-2.0),
        "IBKR2": SymbolMetrics(symbol="IBKR2", fbtot=0.8, ask_sell_pahalilik=-0.1, gort=-2.0),
        "SHRT1": SymbolMetrics(symbol="SHRT1", sfstot=1.8, bid_buy_ucuzluk=0.1, gort=2.0)
    }
    
    # 3. Mock Exposure (Force Eligible)
    exposure = ExposureSnapshot(
        pot_total=100000, pot_max=50000, long_lots=400, short_lots=100, net_exposure=300, mode="DEFANSIF"
    )
    
    # 4. Create Decision Request
    request = DecisionRequest(
        positions=positions,
        metrics=metrics,
        exposure=exposure,
        cycle_count=1,
        snapshot_ts=datetime.now()
    )
    
    # 5. Run Engine
    print(f"\n[INPUT] Sending {len(positions)} positions:")
    print(f"  - Hammer: 3 (HMR1, HMR2, SHRT1)")
    print(f"  - IBKR: 2 (IBKR1, IBKR2)")
    
    print("\n[RUNNING] reducemore_decision_engine...")
    response = await reducemore_decision_engine(request)
    
    print(f"\n[OUTPUT] Engine finished in {response.execution_time_ms:.2f}ms")
    print(f"Decisions Generated: {len(response.decisions)}")
    
    # Note: We rely on the app logger output to see the TRACE log
    # But visually we can confirm it ran without error
    print("\n[VERIFICATION] Check console output above for '[REDUCEMORE_TRACE]' log.")
    print("Expected: 'Longs breakdown: 2 Hammer, 2 IBKR'")

if __name__ == "__main__":
    asyncio.run(verify_pk_awareness())
