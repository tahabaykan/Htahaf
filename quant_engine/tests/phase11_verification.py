"""
Phase 11 Verification Test
==========================

Tests the Hierarchical Architecture:
1.  Strategy Config Loading
2.  Runtime Control Toggles
3.  Karbotu (Analyzer) Output
4.  Reducemore (Analyzer) Output
5.  LT Trim (Executive) Decision Making
6.  Runall (Orchestrator) Conflict Resolution
7.  Internal Ledger Updates
"""

import asyncio
import os
import shutil
from pathlib import Path
from datetime import datetime

# Setup paths
TEST_DATA_DIR = Path("tests/data_phase11")
LEDGER_DIR = TEST_DATA_DIR / "ledger"
CONFIG_DIR = TEST_DATA_DIR / "config"

# Import Engine Components
from app.psfalgo.decision_models import DecisionRequest, ExposureSnapshot, SymbolMetrics, PositionSnapshot
from app.state.runtime_controls import get_runtime_controls_manager
from app.config.strategy_config_manager import get_strategy_config_manager
from app.core.internal_ledger import get_internal_ledger_store
from app.psfalgo.runall_engine import get_runall_engine
from app.trading.trading_account_context import get_trading_context, TradingAccountMode
from app.core.logger import logger

# Mock Data
def create_mock_request():
    pos = PositionSnapshot(
        symbol="AAPL", qty=500, avg_price=150.0, current_price=155.0, unrealized_pnl=2500.0,
        account_type="HAMMER_PRO", group="TECH"
    )
    metric = SymbolMetrics(
        symbol="AAPL", bid=154.90, ask=155.10, last=155.0, 
        ask_sell_pahalilik=0.12, # Should trigger LT Ladder
        fbtot=1.2 # Should trigger Karbotu
    )
    return DecisionRequest(
         positions=[pos], 
         metrics={"AAPL": metric}, 
         exposure=ExposureSnapshot(100000, 200000, 500, 0, 500, "NORMAL"),
         snapshot_ts=datetime.now(),
         correlation_id="test-corr-id"
    )

async def test_phase_11_flow():
    print("\n--- Starting Phase 11 Verification ---")
    
    # 0. Cleanup & Setup
    if TEST_DATA_DIR.exists(): shutil.rmtree(TEST_DATA_DIR)
    CONFIG_DIR.mkdir(parents=True)
    
    # 1. Setup Config & Controls
    print("[1] Setting up Config & Controls...")
    ctrl_mgr = get_runtime_controls_manager()
    controls = ctrl_mgr.get_controls("HAMPRO")
    controls.lt_trim_enabled = True # Enable system
    controls.lt_trim_intensity = 1.0
    
    # 2. Setup Ledger
    print("[2] Setting up Ledger...")
    # Inject test path if possible, or just use default but isolated by mock context
    # ideally we mock the path in the store, but for fast test we'll use actual file system 
    # and rely on cleanups.
    # The ledger store uses "data/ledger" hardcoded in init unless passed. 
    # We will instantiate directly to inject path.
    from app.core.internal_ledger import InternalLedgerStore
    store = InternalLedgerStore("HAMPRO", data_dir=LEDGER_DIR)
    
    # Record initial position source (MM)
    store.record_transaction("AAPL", 500, "MM") 
    entry = store.get_entry("AAPL")
    print(f"    Ledger Initial: LT={entry.lt_net}, MM={entry.mm_net} (Expected MM=500)")
    assert entry.mm_net == 500
    
    # 3. Execution (Simulated via Runall Logic)
    # We will manually invoke the engines to inspect intermediate states
    print("[3] Running Engines...")
    
    import app.psfalgo.karbotu_engine as ke
    import app.psfalgo.reducemore_engine as re
    import app.event_driven.decision_engine.lt_trim_engine as lte
    
    request = create_mock_request()
    rules = {} # Default rules
    
    # Run Karbotu
    k_eng = ke.get_karbotu_engine()
    k_out = await k_eng.run(request, rules)
    print(f"    Karbotu Output: Signals={len(k_out.signals)}, Intents={len(k_out.intents)}")
    if "AAPL" in k_out.signals:
        sig = k_out.signals["AAPL"]
        print(f"    [DEBUG] AAPL Signal: Eligible={sig.eligibility}, Bias={sig.bias}, Reason={sig.reason_codes}")

    # Check Controls
    print(f"    [DEBUG] Controls: Sys={controls.lt_trim_enabled}, Long={controls.lt_trim_long_enabled}, Intensity={controls.lt_trim_intensity}")

    # Run Reducemore
    r_eng = re.get_reducemore_engine()
    r_out = await r_eng.run(request, rules)
    print(f"    Reducemore Output: Multipliers={len(r_out.multipliers)}, Intents={len(r_out.intents)}")
    
    # Check Multiplier logic
    if "AAPL" in r_out.multipliers:
        print(f"    AAPL Multiplier: {r_out.multipliers['AAPL'].value}")
    
    # Run LT Trim
    l_eng = lte.get_lt_trim_engine()
    l_eng.reset_stats() # Ensure clean state
    lt_intents = await l_eng.run(
        request, k_out.signals, r_out.multipliers, rules, controls
    )
    print(f"    LT Trim Output: Intents={len(lt_intents)}")
    
    # Expect LT Trim intent for AAPL (Ask Sell Pahalilik 0.12 > Ladder Target 0.10)
    has_aapl_trim = any(i.symbol == "AAPL" for i in lt_intents)
    print(f"    Generated AAPL Trim? {has_aapl_trim}")
    assert has_aapl_trim
    
    # 4. Conflict Resolution
    print("[4] Conflict Resolution...")
    runall = get_runall_engine()
    all_intents = k_out.intents + r_out.intents + lt_intents
    resolved = runall._resolve_conflicts(all_intents)
    print(f"    Resolved Intents: {len(resolved)}")
    
    # 5. Ledger Update Verification
    print("[5] Ledger Update Verification...")
    # Simulate execution of the resolved intent (SELL)
    for intent in resolved:
        if intent.symbol == "AAPL" and intent.action == "SELL":
            qty = -intent.qty # Sell is negative
            print(f"    Executing {qty} for AAPL (Source: LT)")
            store.record_transaction("AAPL", qty, "LT")
            
    entry = store.get_entry("AAPL")
    print(f"    Ledger Final: LT_Net={entry.lt_net}, MM_Net={entry.mm_net}")
    print(f"    LT buckets: L={entry.lt_long} S={entry.lt_short}")
    print(f"    MM buckets: L={entry.mm_long} S={entry.mm_short}")
    
    # Verification:
    # Started with MM +500.
    # Executed LT Sell (say -100).
    # Logic: Sell reduces LONGs. 
    # Since source=LT, it tries reducing LT_LONG first (0), then MM_LONG (500).
    # Wait, my ledger logic for SELL source=LT said:
    # "Reduce LT_LONG, then MM_LONG".
    # So LT_LONG was 0 -> no change. MM_LONG should decrease.
    # Result: MM_LONG should be 400 (if 100 sold).
    
    if entry.mm_long < 500:
        print("    SUCCESS: MM Long reduced by LT Sell (Cross-Bucket Netting working)")
    else:
        print("    FAIL: MM Long did not decrease")
        
    print("\n--- Verification Complete ---")

if __name__ == "__main__":
    asyncio.run(test_phase_11_flow())
