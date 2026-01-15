"""
Shadow Smoke Test - Phase 8

End-to-end dry run test without FastAPI.
Tests decision→proposal pipeline with real market snapshots.

Key Principles:
- FastAPI running değilse bile çalışır
- Internal çağrılarla test eder
- Mock positions kullanır
- Real market snapshot üzerinden çalışır
- Console'a örnek proposal basar
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

# Add quant_engine to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.logger import logger
from app.psfalgo.market_snapshot_store import initialize_market_snapshot_store, get_market_snapshot_store
from app.psfalgo.metric_compute_engine import initialize_metric_compute_engine, get_metric_compute_engine
from app.psfalgo.data_readiness_checker import initialize_data_readiness_checker, get_data_readiness_checker
from app.psfalgo.runall_engine import initialize_runall_engine, get_runall_engine
from app.psfalgo.position_snapshot_api import get_position_snapshot_api
from app.psfalgo.metrics_snapshot_api import get_metrics_snapshot_api, initialize_metrics_snapshot_api
from app.psfalgo.exposure_calculator import get_exposure_calculator, initialize_exposure_calculator
from app.psfalgo.karbotu_engine import karbotu_decision_engine
from app.psfalgo.reducemore_engine import reducemore_decision_engine
from app.psfalgo.addnewpos_engine import addnewpos_decision_engine
from app.psfalgo.proposal_engine import initialize_proposal_engine, get_proposal_engine
from app.psfalgo.proposal_store import initialize_proposal_store, get_proposal_store
from app.psfalgo.decision_models import DecisionRequest, PositionSnapshot, ExposureSnapshot
from app.api.websocket_routes import get_static_store, get_market_data_cache
from app.api.market_data_routes import initialize_market_data_services


async def shadow_smoke_test():
    """Run shadow smoke test"""
    print("=" * 80)
    print("SHADOW SMOKE TEST - End-to-End Dry Run")
    print("=" * 80)
    print()
    
    # Initialize services
    print("1. Initializing services...")
    initialize_market_data_services()
    initialize_market_snapshot_store()
    initialize_metric_compute_engine()
    initialize_data_readiness_checker()
    initialize_exposure_calculator()
    initialize_proposal_engine()
    initialize_proposal_store(max_proposals=100)
    
    # Get services
    static_store = get_static_store()
    market_data_cache = get_market_data_cache()
    snapshot_store = get_market_snapshot_store()
    compute_engine = get_metric_compute_engine()
    proposal_engine = get_proposal_engine()
    proposal_store = get_proposal_store()
    
    if not static_store or not static_store.is_loaded():
        print("ERROR: Static store not loaded. Please load CSV first.")
        return
    
    # Get symbols
    all_symbols = static_store.get_all_symbols()
    test_symbols = all_symbols[:20]  # First 20 symbols for testing
    
    print(f"   Loaded {len(all_symbols)} symbols, testing with {len(test_symbols)} symbols")
    print()
    
    # Create mock snapshots for test symbols
    print("2. Creating mock market snapshots...")
    snapshot_count = 0
    for symbol in test_symbols:
        # Get market data
        market_data = market_data_cache.get(symbol, {})
        if not market_data:
            continue
        
        # Get static data
        static_data = static_store.get_static_data(symbol)
        if not static_data:
            continue
        
        # Mock position data
        position_data = {
            'qty': 0.0,  # No position
            'cost': 0.0,
            'befday_qty': 0.0,
            'befday_cost': 0.0
        }
        
        # Compute metrics and create snapshot
        snapshot = compute_engine.compute_metrics(
            symbol=symbol,
            market_data=market_data,
            position_data=position_data,
            static_data=static_data
        )
        
        # Update snapshot store
        await snapshot_store.update_current_snapshot(symbol, snapshot, account_type='IBKR_GUN')
        snapshot_count += 1
    
    print(f"   Created {snapshot_count} market snapshots")
    print()
    
    # Check data readiness
    print("3. Checking data readiness...")
    checker = get_data_readiness_checker()
    if checker:
        report = checker.check_data_readiness()
        print(f"   Market snapshot store ready: {report['market_snapshot_store_ready']}")
        print(f"   Symbols with live prices: {report['symbols_with_live_prices']}")
        print(f"   Symbols with prev_close: {report['symbols_with_prev_close']}")
        print(f"   Symbols with fbtot: {report['symbols_with_fbtot']}")
        print(f"   Symbols with gort: {report['symbols_with_gort']}")
        print()
    
    # Initialize metrics snapshot API
    print("4. Initializing metrics snapshot API...")
    initialize_metrics_snapshot_api(
        market_data_cache=market_data_cache,
        static_store=static_store
    )
    metrics_api = get_metrics_snapshot_api()
    print("   Metrics snapshot API initialized")
    print()
    
    # Create mock positions for testing
    print("5. Creating mock positions...")
    mock_positions = [
        PositionSnapshot(
            symbol=test_symbols[0] if test_symbols else "MS PRK",
            qty=400.0,
            avg_price=27.00,
            current_price=27.30,
            unrealized_pnl=120.0,
            group="heldff",
            cgrup=None,
            timestamp=datetime.now()
        )
    ]
    print(f"   Created {len(mock_positions)} mock positions")
    print()
    
    # Calculate exposure
    print("6. Calculating exposure...")
    exposure_calc = get_exposure_calculator()
    exposure = exposure_calc.calculate_exposure(mock_positions)
    print(f"   Pot Total: {exposure.pot_total:,.0f}")
    print(f"   Pot Max: {exposure.pot_max:,.0f}")
    print(f"   Exposure Ratio: {exposure.exposure_ratio*100:.2f}%")
    print(f"   Mode: {exposure.exposure_mode}")
    print()
    
    # Get metrics snapshot
    print("7. Getting metrics snapshot...")
    snapshot_ts = datetime.now()
    symbols = [p.symbol for p in mock_positions]
    metrics = await metrics_api.get_metrics_snapshot(symbols, snapshot_ts=snapshot_ts)
    print(f"   Got metrics for {len(metrics)} symbols")
    print()
    
    # Run KARBOTU
    print("8. Running KARBOTU decision engine...")
    karbotu_request = DecisionRequest(
        positions=mock_positions,
        metrics=metrics,
        exposure=exposure,
        cycle_count=1,
        snapshot_ts=snapshot_ts
    )
    karbotu_response = await karbotu_decision_engine(karbotu_request)
    print(f"   KARBOTU: {len(karbotu_response.decisions)} decisions, {len(karbotu_response.filtered_out)} filtered")
    print()
    
    # Generate proposals from KARBOTU
    if karbotu_response.decisions:
        print("9. Generating proposals from KARBOTU decisions...")
        proposals = await proposal_engine.process_decision_response(
            response=karbotu_response,
            cycle_id=1,
            decision_source='KARBOTU',
            decision_timestamp=snapshot_ts
        )
        
        # Store proposals
        for proposal in proposals:
            proposal_store.add_proposal(proposal)
        
        print(f"   Generated {len(proposals)} proposals")
        print()
    
    # Display top 5 proposals
    print("10. Top 5 Recent Proposals:")
    print("=" * 80)
    recent_proposals = proposal_store.get_latest_proposals(limit=5)
    for i, prop in enumerate(recent_proposals, 1):
        print(f"\nProposal {i}:")
        print(f"  Symbol: {prop.symbol}")
        print(f"  Action: {prop.side} {prop.qty} @ {prop.proposed_price or 'MARKET'} ({prop.order_type})")
        print(f"  Market: Bid=${prop.bid:.2f}, Ask=${prop.ask:.2f}, Last=${prop.last:.2f}, Spread={prop.spread_percent:.2f}%")
        print(f"  Reason: {prop.reason[:80]}..." if len(prop.reason) > 80 else f"  Reason: {prop.reason}")
        print(f"  Confidence: {prop.confidence:.2%}")
        print(f"  Engine: {prop.engine}")
        if hasattr(prop, 'warnings') and prop.warnings:
            print(f"  Warnings: {', '.join(prop.warnings)}")
        print(f"  Metrics Used: {list(prop.metrics_used.keys())[:5]}...")  # First 5 keys
    
    print()
    print("=" * 80)
    print("[OK] Shadow smoke test complete")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(shadow_smoke_test())






