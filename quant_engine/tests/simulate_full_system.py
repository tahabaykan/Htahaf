import asyncio
import sys
import os
import random
from datetime import datetime, timedelta
# Add project root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mocks & Overrides
from unittest.mock import MagicMock, patch

# Core components
from app.psfalgo.runall_engine import get_runall_engine
from app.psfalgo.order_manager import initialize_order_controller, TrackedOrder, OrderStatus
from app.trading.trading_account_context import get_trading_context, TradingAccountMode
from app.state.runtime_controls import get_runtime_controls_manager, AccountRuntimeControls
from app.config.strategy_config_manager import get_strategy_config_manager
from app.psfalgo.decision_models import DecisionRequest, ExposureSnapshot, SymbolMetrics, PositionSnapshot
from app.core.internal_ledger import get_internal_ledger_store, InternalLedgerStore, _ledger_stores, LedgerEntry
from pathlib import Path

async def run_simulation():
    print("🚀 Starting FULL SYSTEM SIMULATION (Phase 11.5)...")
    
    # 1. Initialize State
    initialize_order_controller()
    
    # Manually Init Ledger for Test
    test_ledger_dir = Path("tests/sim_data")
    if test_ledger_dir.exists():
        import shutil
        shutil.rmtree(test_ledger_dir)
    test_ledger_dir.mkdir(parents=True, exist_ok=True)
    
    # Pre-seed ledger if needed, or clean start
    _ledger_stores["HAMPRO"] = InternalLedgerStore("HAMPRO", data_dir=test_ledger_dir)
    
    # Setup Trading Context
    ctx = get_trading_context()
    ctx.set_trading_mode(TradingAccountMode.HAMPRO)
    
    # Setup Controls
    ctrl_mgr = get_runtime_controls_manager()
    updates = {
        "system_enabled": True,
        "lt_trim_long_enabled": True,
        "lt_trim_short_enabled": True
    }
    ctrl_mgr.update_controls("HAMPRO", updates)
    
    # Setup Rules
    cfg_mgr = get_strategy_config_manager() # Use default mocked in other tests or standard?
    # For simulation, we assume defaults are loadable or we mock get_effective_rules
    
    runall = get_runall_engine()
    
    # 2. Mock Data Generator
    # We need to block _prepare_request and inject our own scenarios
    
    scenarios = [
        {
            "name": "Cycle 1: Calm Market",
            "spread": 0.01,
            "exposure": 10000.0,
            "positions": [
                # AAPL: Profitable, Score High -> Keep/Add?
                # TSLA: Losing, Score Low -> Trim?
                PositionSnapshot(symbol="TSLA", qty=1000, avg_price=200.0, current_price=190.0, unrealized_pnl=-10000.0, account_type="HAMPRO")
            ]
        },
        {
            "name": "Cycle 2: Volatility Spike (Spread Widens)",
            "spread": 0.05, # High spread -> Karbotu Veto?
            "exposure": 10000.0,
            "positions": [
                PositionSnapshot(symbol="TSLA", qty=1000, avg_price=200.0, current_price=185.0, unrealized_pnl=-15000.0, account_type="HAMPRO")
            ]
        },
        {
            "name": "Cycle 3: Risk Event (High Exposure)",
            "spread": 0.02,
            "exposure": 150000.0, # High Exposure -> Reducemore Multiplier?
            "positions": [
                PositionSnapshot(symbol="TSLA", qty=1000, avg_price=200.0, current_price=180.0, unrealized_pnl=-20000.0, account_type="HAMPRO")
            ]
        }
    ]

    # Mock _prepare_request to return scenario data
    async def mock_prepare_request(account_id, correlation_id):
        scenario = scenarios.pop(0) if scenarios else None
        if not scenario: return None
        
        print(f"\n--- {scenario['name']} ---")
        
        # Create Metrics
        metrics = {
            "TSLA": SymbolMetrics(
                symbol="TSLA", 
                bid=190.0, 
                ask=190.0 + scenario['spread'], 
                last=190.0,
                spread=scenario['spread'], 
                prev_close=200.0,
                # avg_volume and atr aren't in SymbolMetrics, skipping or using generic fields if available
                # Assuming generic fields are sufficient for decision engine
                ask_sell_pahalilik=0.15 # Ensure it triggers logic
            )
        }
        # Fake logic for score injection:
        # We need to mock the *analyzers* if we want total control, 
        # OR we let analyzers run on this data.
        # Let's let them run but assume analyzers pull scores from 'l1_data' or similar.
        # Ideally, we mock the 'AnalysisSignal' etc if we want to test Runall primarily.
        # BUT User wants to see Karbotu/Reducemore behavior. 
        # So we must provide data they consume.
        
        return DecisionRequest(
            positions=scenario['positions'],
            metrics=metrics,
            exposure=ExposureSnapshot(
                pot_total=200000.0, 
                pot_max=1000000.0,
                long_lots=1000, 
                short_lots=0,
                net_exposure=scenario['exposure'], 
                mode="OFANSIF"
            ),
            snapshot_ts=datetime.now(),
            correlation_id=correlation_id,
            l1_data=metrics # Passing metrics as l1_data for analyzers
        )

    # Patch Request Preparation
    with patch.object(runall, '_prepare_request', side_effect=mock_prepare_request):
        
        # --- CYCLE 1 ---
        # Mocking existing Open Orders for Cancel verification
        oc = initialize_order_controller()
        o1 = TrackedOrder(order_id="stale_1", symbol="TSLA", action="SELL", order_type="LIMIT", lot_qty=100, price=205.0, provider="HAMPRO", book="LT")
        oc.track_order(o1)
        
        print(f"Pre-Cycle 1 Active Orders: {len(oc.get_active_orders('HAMPRO'))}")
        
        intents_1 = await runall.run_single_cycle()
        
        # Verify Cancellation
        print(f"Post-Cycle 1 Active Orders: {len(oc.get_active_orders('HAMPRO'))} (Should be 0 BEFORE new ones are sent)")
        print(f"Intents Generated: {len(intents_1)}")
        for i in intents_1: print(f"  -> {i.intent_category}: {i.symbol} {i.action} {i.qty}")

        # --- CYCLE 2 ---
        # Spread Widens -> Karbotu should block or reduce aggression?
        # Mock that Cycle 1 orders are now 'Open' again (replacing what ExecutionEngine would do)
        if intents_1:
            o2 = TrackedOrder(order_id="fresh_1", symbol="TSLA", action="SELL", order_type="LIMIT", lot_qty=intents_1[0].qty, price=190.0, provider="HAMPRO", book="LT")
            oc.track_order(o2)
        
        intents_2 = await runall.run_single_cycle()
        print(f"Intents Generated (Volatile): {len(intents_2)}")
        
        # --- CYCLE 3 ---
        # High Risk -> Reducemore should scale up?
        if intents_2:
            o3 = TrackedOrder(order_id="fresh_2", symbol="TSLA", action="SELL", order_type="LIMIT", lot_qty=intents_2[0].qty, provider="HAMPRO", book="LT", price=185.0)
            oc.track_order(o3)
            
        intents_3 = await runall.run_single_cycle()
        print(f"Intents Generated (High Risk): {len(intents_3)}")
        for i in intents_3: print(f"  -> {i.intent_category}: {i.symbol} {i.qty} (Priority: {i.priority})")

if __name__ == "__main__":
    asyncio.run(run_simulation())
