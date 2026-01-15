"""
Market Data API Routes
Endpoints for merged data: static CSV + live Hammer market data + derived scores
"""

from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any, Optional
from collections import deque
import os
from pathlib import Path

from app.core.logger import logger
from app.config.settings import settings
from app.market_data.static_data_store import StaticDataStore, get_static_store
from app.market_data.derived_metrics_engine import DerivedMetricsEngine
from app.market_data.symbol_state import SymbolStateEngine
from app.market_data.janall_metrics_engine import JanallMetricsEngine
from app.market_data.benchmark_engine import BenchmarkEngine
from app.market_data.rank_engine import RankEngine
from app.market_data.grpan_engine import GRPANEngine
from app.market_data.trade_print_router import TradePrintRouter
from app.market_data.grpan_tick_fetcher import GRPANTickFetcher
from app.market_data.rwvap_engine import initialize_rwvap_engine, get_rwvap_engine
from app.market_data.pricing_overlay_engine import PricingOverlayEngine
from app.market_data.position_analytics_engine import PositionAnalyticsEngine
from app.decision.exposure_mode_engine import ExposureModeEngine
from app.psfalgo.position_snapshot_engine import PositionSnapshotEngine
from app.psfalgo.position_guard_engine import PositionGuardEngine
from app.psfalgo.action_planner import PSFALGOActionPlanner
from app.decision.intent_engine import IntentEngine
from app.decision.order_planner import OrderPlanner
from app.decision.order_queue import OrderQueue
from app.decision.order_gate import OrderGate
from app.decision.user_action_store import UserActionStore
from app.decision.signal_interpreter import SignalInterpreter
from app.execution.execution_router import ExecutionRouter, ExecutionMode

# Global instances (will be initialized)
static_store: Optional[StaticDataStore] = None
metrics_engine: Optional[DerivedMetricsEngine] = None
janall_metrics_engine: Optional[JanallMetricsEngine] = None
benchmark_engine: Optional[BenchmarkEngine] = None
rank_engine: Optional[RankEngine] = None
grpan_engine: Optional[GRPANEngine] = None
rwvap_engine = None  # RWVAPEngine instance
trade_print_router: Optional[TradePrintRouter] = None
# 🔵 CRITICAL: grpan_tick_fetcher is now ONLY handled by worker process
# Backend does NOT use GRPANTickFetcher to avoid blocking terminal
# Worker (deeper_analysis_worker.py) has its own GRPANTickFetcher instance
grpan_tick_fetcher: Optional[GRPANTickFetcher] = None  # Always None in backend
position_analytics_engine: Optional[PositionAnalyticsEngine] = None
exposure_mode_engine: Optional[ExposureModeEngine] = None
position_snapshot_engine: Optional[PositionSnapshotEngine] = None
position_guard_engine: Optional[PositionGuardEngine] = None
psfalgo_action_planner: Optional[PSFALGOActionPlanner] = None
state_engine: Optional[SymbolStateEngine] = None
intent_engine: Optional[IntentEngine] = None
order_planner: Optional[OrderPlanner] = None
order_queue: Optional[OrderQueue] = None
order_gate: Optional[OrderGate] = None
user_action_store: Optional[UserActionStore] = None
signal_interpreter: Optional[SignalInterpreter] = None
execution_router: Optional[ExecutionRouter] = None
pricing_overlay_engine = None  # PricingOverlayEngine instance
market_data_cache: Dict[str, Dict[str, Any]] = {}  # {symbol: market_data}
etf_market_data: Dict[str, Dict[str, Any]] = {}  # {symbol: etf_data} - Isolated from scanner logic

# Dirty tracking for WebSocket optimization (only broadcast changed symbols)
_dirty_symbols: set = set()  # Symbols that have been updated since last broadcast
etf_prev_close: Dict[str, float] = {}  # {ETF: prev_close} - Loaded from janeketfs.csv at startup

# ETF tickers to track
ETF_TICKERS = ['TLT', 'IEF', 'IEI', 'PFF', 'PGF', 'KRE', 'IWM', 'SPY']

# Global hammer_feed instance (set by main.py or external process)
_hammer_feed_instance = None

def set_hammer_feed(hammer_feed):
    """Set global hammer_feed instance (called by main.py)"""
    global _hammer_feed_instance
    _hammer_feed_instance = hammer_feed
    logger.info("Hammer feed instance set for ETF subscription")

def get_hammer_feed():
    """Get global hammer_feed instance"""
    return _hammer_feed_instance

def get_hammer_client():
    """Get Hammer client from hammer_feed instance"""
    hammer_feed = get_hammer_feed()
    if hammer_feed and hasattr(hammer_feed, 'hammer_client'):
        return hammer_feed.hammer_client
    return None

router = APIRouter(prefix="/api/market-data", tags=["market-data"])


@router.get("/grpan/state/{symbol}")
async def get_grpan_state(symbol: str):
    """
    Get GRPAN state for a symbol (all windows).
    
    Returns:
        Dict with latest_pan and all rolling windows (pan_10m, pan_30m, pan_1h, pan_3h, pan_1d, pan_3d)
    """
    try:
        # Services already initialized at startup
        grpan_engine = get_grpan_engine()
        if not grpan_engine:
            raise HTTPException(status_code=500, detail="GRPANEngine not initialized")
        
        # Get all windows for symbol
        all_windows = grpan_engine.get_all_windows_for_symbol(symbol)
        
        if not all_windows:
            return {
                "success": True,
                "symbol": symbol,
                "latest_pan": None,
                "pan_10m": None,
                "pan_30m": None,
                "pan_1h": None,
                "pan_3h": None,
                "pan_1d": None,
                "pan_3d": None,
                "message": "No GRPAN data available for this symbol"
            }
        
        return {
            "success": True,
            "symbol": symbol,
            "latest_pan": all_windows.get('latest_pan', {}),
            "pan_10m": all_windows.get('pan_10m', {}),
            "pan_30m": all_windows.get('pan_30m', {}),
            "pan_1h": all_windows.get('pan_1h', {}),
            "pan_3h": all_windows.get('pan_3h', {}),
            "pan_1d": all_windows.get('pan_1d', {}),
            "pan_3d": all_windows.get('pan_3d', {})
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting GRPAN state for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rwvap/{symbol}")
async def get_rwvap_for_symbol(symbol: str):
    """
    Get all RWVAP windows for a single symbol.
    
    Args:
        symbol: PREF_IBKR symbol
        
    Returns:
        Dict containing RWVAP data for all windows (rwvap_1d, rwvap_3d, rwvap_5d)
    """
    try:
        # Services already initialized at startup
        rwvap_engine = get_rwvap_engine()
        if not rwvap_engine:
            raise HTTPException(status_code=500, detail="RWVAPEngine not initialized")
        
        rwvap_data = rwvap_engine.get_all_rwvap_for_symbol(symbol)
        if not rwvap_data:
            raise HTTPException(status_code=404, detail=f"RWVAP data not found for {symbol}")
        
        return {"success": True, "data": rwvap_data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting RWVAP for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/grpan/debug")
async def get_grpan_debug():
    """
    Get GRPAN engine debug information.
    
    Returns:
        GRPAN engine status, metrics, and sample data (including rolling windows)
    """
    try:
        grpan_engine = get_grpan_engine()
        if not grpan_engine:
            return {
                "success": False,
                "error": "GRPANEngine not initialized"
            }
        
        # Get metrics
        metrics = grpan_engine.get_metrics()
        
        # Get sample symbols with GRPAN data (all windows)
        sample_symbols = list(grpan_engine.trade_prints_store.keys())[:10]
        sample_data = {}
        for symbol in sample_symbols:
            prints_count = len(grpan_engine.trade_prints_store.get(symbol, deque()))
            latest_pan = grpan_engine.get_grpan_for_symbol(symbol)  # latest_pan
            all_windows = grpan_engine.get_all_windows_for_symbol(symbol)  # All windows
            
            sample_data[symbol] = {
                'prints_in_buffer': prints_count,
                'latest_pan': {
                    'grpan_price': latest_pan.get('grpan_price'),
                    'concentration_percent': latest_pan.get('concentration_percent'),
                    'print_count': latest_pan.get('print_count'),
                    'real_lot_count': latest_pan.get('real_lot_count')
                },
                'rolling_windows': {
                    'pan_10m': {
                        'grpan_price': all_windows.get('pan_10m', {}).get('grpan_price'),
                        'concentration_percent': all_windows.get('pan_10m', {}).get('concentration_percent'),
                        'deviation_vs_last': all_windows.get('pan_10m', {}).get('deviation_vs_last'),
                        'print_count': all_windows.get('pan_10m', {}).get('print_count')
                    },
                    'pan_30m': {
                        'grpan_price': all_windows.get('pan_30m', {}).get('grpan_price'),
                        'concentration_percent': all_windows.get('pan_30m', {}).get('concentration_percent'),
                        'deviation_vs_last': all_windows.get('pan_30m', {}).get('deviation_vs_last'),
                        'print_count': all_windows.get('pan_30m', {}).get('print_count')
                    },
                    'pan_1h': {
                        'grpan_price': all_windows.get('pan_1h', {}).get('grpan_price'),
                        'concentration_percent': all_windows.get('pan_1h', {}).get('concentration_percent'),
                        'deviation_vs_last': all_windows.get('pan_1h', {}).get('deviation_vs_last'),
                        'print_count': all_windows.get('pan_1h', {}).get('print_count')
                    },
                    'pan_3h': {
                        'grpan_price': all_windows.get('pan_3h', {}).get('grpan_price'),
                        'concentration_percent': all_windows.get('pan_3h', {}).get('concentration_percent'),
                        'deviation_vs_last': all_windows.get('pan_3h', {}).get('deviation_vs_last'),
                        'print_count': all_windows.get('pan_3h', {}).get('print_count')
                    },
                    'pan_1d': {
                        'grpan_price': all_windows.get('pan_1d', {}).get('grpan_price'),
                        'concentration_percent': all_windows.get('pan_1d', {}).get('concentration_percent'),
                        'deviation_vs_last': all_windows.get('pan_1d', {}).get('deviation_vs_last'),
                        'print_count': all_windows.get('pan_1d', {}).get('print_count')
                    },
                    'pan_3d': {
                        'grpan_price': all_windows.get('pan_3d', {}).get('grpan_price'),
                        'concentration_percent': all_windows.get('pan_3d', {}).get('concentration_percent'),
                        'deviation_vs_last': all_windows.get('pan_3d', {}).get('deviation_vs_last'),
                        'print_count': all_windows.get('pan_3d', {}).get('print_count')
                    }
                }
            }
        
        return {
            "success": True,
            "metrics": metrics,
            "total_symbols_with_prints": len(grpan_engine.trade_prints_store),
            "dirty_symbols_count": len(grpan_engine.dirty_symbols),
            "sample_data": sample_data,
            "config": {
                "max_prints": grpan_engine.max_prints,
                "min_lot_size": grpan_engine.min_lot_size,
                "compute_interval_ms": grpan_engine.compute_interval_ms,
                "rolling_windows": list(grpan_engine.ROLLING_WINDOWS.keys())
            }
        }
    except Exception as e:
        logger.error(f"Error getting GRPAN debug info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/etf")
async def get_etf_data():
    """
    Get ETF benchmark data (isolated from scanner logic)
    
    Returns:
        List of ETF records with last, prev_close, daily_change_percent, daily_change_cents
    """
    try:
        global etf_market_data
        etf_list = list(etf_market_data.values())
        return {
            "success": True,
            "data": etf_list,
            "count": len(etf_list)
        }
    except Exception as e:
        logger.error(f"Error getting ETF data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subscribe-etf")
async def subscribe_etf():
    """
    Subscribe to ETF tickers via Hammer feed
    
    Returns:
        Success status and subscribed count
    """
    try:
        hammer_feed = get_hammer_feed()
        if not hammer_feed:
            logger.warning("Hammer feed not available - ETF subscription skipped")
            return {
                "success": True,  # Return success even if Hammer not available
                "message": "Hammer feed not available. ETF subscription requires active Hammer connection.",
                "subscribed": 0,
                "total": len(ETF_TICKERS)
            }
        
        subscribed_count = 0
        for symbol in ETF_TICKERS:
            try:
                # Subscribe to L1 only (User confirmed L2 not needed for ETFs)
                # verified: Benchmark logic only needs Last/PrevClose (L1)
                if hammer_feed.subscribe_symbol(symbol, include_l2=False):
                    subscribed_count += 1
                    logger.info(f"✅ Subscribed to ETF: {symbol} (L1 only)")
                else:
                    logger.warning(f"⚠️ Failed to subscribe to ETF: {symbol}")
            except Exception as e:
                logger.error(f"Error subscribing to ETF {symbol}: {e}")
        
        return {
            "success": True,
            "message": f"Subscribed to {subscribed_count}/{len(ETF_TICKERS)} ETFs",
            "subscribed": subscribed_count,
            "total": len(ETF_TICKERS)
        }
    except Exception as e:
        logger.error(f"Error subscribing to ETFs: {e}", exc_info=True)
        # Return success with error message instead of raising exception
        return {
            "success": True,
            "message": f"Error subscribing to ETFs: {str(e)}",
            "subscribed": 0,
            "total": len(ETF_TICKERS)
        }


@router.post("/subscribe-preferred")
async def subscribe_preferred():
    """
    Subscribe to all preferred stocks via Hammer feed (L1 only).
    
    This endpoint is called when Scanner page loads to subscribe to all preferred symbols.
    Only L1 subscription (bid/ask/last) - L2 is not needed for preferred stocks.
    
    Returns:
        Success status and subscribed count
    """
    logger.info("📊 [SUBSCRIBE_PREFERRED] Endpoint called - starting preferred stock subscription")
    
    try:
        hammer_feed = get_hammer_feed()
        if not hammer_feed:
            logger.warning("⚠️ [SUBSCRIBE_PREFERRED] Hammer feed not available - Preferred subscription skipped")
            return {
                "success": False,
                "message": "Hammer feed not available. Preferred subscription requires active Hammer connection.",
                "subscribed": 0
            }
        
        # Check if Hammer client is connected
        hammer_client = get_hammer_client()
        if not hammer_client or not hammer_client.is_connected():
            logger.warning("⚠️ [SUBSCRIBE_PREFERRED] Hammer client not connected - Preferred subscription skipped")
            return {
                "success": False,
                "message": "Hammer client not connected. Please wait for Hammer connection.",
                "subscribed": 0
            }
        
        logger.info("✅ [SUBSCRIBE_PREFERRED] Hammer feed and client are available")
        
        # Services already initialized at startup
        # Get all preferred symbols from static_store (use global instance)
        global static_store
        if not static_store or not static_store.is_loaded():
            logger.warning("⚠️ [SUBSCRIBE_PREFERRED] Static store not loaded - Preferred subscription skipped")
            return {
                "success": False,
                "message": "Static store not loaded. Please load CSV first.",
                "subscribed": 0
            }
        
        # Get all symbols (exclude ETFs - they are subscribed separately)
        all_symbols = static_store.get_all_symbols()
        preferred_symbols = [s for s in all_symbols if s not in ETF_TICKERS]
        
        if not preferred_symbols:
            logger.warning("⚠️ [SUBSCRIBE_PREFERRED] No preferred symbols found in static store")
            return {
                "success": False,
                "message": "No preferred symbols found",
                "subscribed": 0,
                "total": 0
            }
        
        logger.info(f"📊 [SUBSCRIBE_PREFERRED] Subscribing to {len(preferred_symbols)} preferred stocks (L1 only)...")
        
        # Subscribe in batches (L1 only, no L2)
        subscribed_count = hammer_feed.subscribe_symbols_batch(
            preferred_symbols,
            include_l2=False,  # L1 only for preferred stocks
            batch_size=50
        )
        
        logger.info(f"✅ [SUBSCRIBE_PREFERRED] Preferred subscription complete: {subscribed_count}/{len(preferred_symbols)} symbols (L1 only)")
        
        return {
            "success": True,
            "message": f"Subscribed to {subscribed_count}/{len(preferred_symbols)} preferred stocks (L1 only)",
            "subscribed": subscribed_count,
            "total": len(preferred_symbols)
        }
    except Exception as e:
        logger.error(f"❌ [SUBSCRIBE_PREFERRED] Error subscribing to preferred stocks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Flag to ensure CSV is only loaded once at startup
_etf_prev_close_loaded = False

def load_etf_prev_close_from_csv():
    """
    Load ETF prev_close values from janeketfs.csv (bootstrap-only, called at startup).
    
    ⚠️ CRITICAL: This function should ONLY be called at startup.
    Runtime CSV reads are FORBIDDEN for trading-grade performance.
    
    Returns:
        Dict[str, float]: {ETF: prev_close} mapping
    """
    global etf_prev_close, _etf_prev_close_loaded
    
    # Guard: Only load once
    if _etf_prev_close_loaded:
        return etf_prev_close
    
    etf_prev_close_loaded = {}
    
    try:
        import pandas as pd
        from pathlib import Path
        
        # Try to find janeketfs.csv in current directory or parent directory
        csv_paths = [
            Path("janeketfs.csv"),
            Path("../janeketfs.csv"),
            Path("../../janeketfs.csv"),
        ]
        
        csv_path = None
        for path in csv_paths:
            if path.exists():
                csv_path = path
                break
        
        if csv_path and csv_path.exists():
            logger.info(f"📊 Loading ETF prev_close from {csv_path}")
            df = pd.read_csv(csv_path)
            
            # Check if required columns exist
            if 'Symbol' in df.columns and 'prev_close' in df.columns:
                for _, row in df.iterrows():
                    symbol = str(row['Symbol']).strip()
                    prev_close_val = row.get('prev_close')
                    
                    if pd.notna(prev_close_val):
                        try:
                            prev_close_float = float(prev_close_val)
                            if prev_close_float > 0:
                                etf_prev_close_loaded[symbol] = prev_close_float
                                logger.debug(f"✅ ETF {symbol}: prev_close={prev_close_float} loaded from CSV")
                        except (ValueError, TypeError):
                            logger.warning(f"⚠️ ETF {symbol}: Invalid prev_close value: {prev_close_val}")
                
                logger.info(f"✅ Loaded {len(etf_prev_close_loaded)} ETF prev_close values from CSV")
            else:
                logger.warning(f"⚠️ {csv_path} does not have 'Symbol' or 'prev_close' columns")
        else:
            logger.warning(f"⚠️ janeketfs.csv not found (tried: {csv_paths})")
            
    except Exception as e:
        logger.warning(f"⚠️ Could not load ETF prev_close from CSV: {e}")
    
    # Update global etf_prev_close dict
    etf_prev_close.update(etf_prev_close_loaded)
    
    # Mark as loaded (prevent future loads)
    _etf_prev_close_loaded = True
    
    return etf_prev_close_loaded


# Flag to ensure services are only initialized once
_market_data_services_initialized = False

def initialize_market_data_services():
    """
    Initialize market data services.
    
    ⚠️ CRITICAL: This should ONLY be called at startup (main.py startup_event).
    Calling this on every request causes CSV reloads and performance issues.
    """
    global static_store, metrics_engine, janall_metrics_engine, benchmark_engine, rank_engine, grpan_engine, rwvap_engine, trade_print_router, grpan_tick_fetcher, position_analytics_engine, exposure_mode_engine, position_snapshot_engine, position_guard_engine, psfalgo_action_planner, state_engine, intent_engine, order_planner, order_queue, order_gate, user_action_store, signal_interpreter, execution_router, pricing_overlay_engine, _market_data_services_initialized
    
    # Guard: Only initialize once
    if _market_data_services_initialized:
        return
    
    # Load ETF prev_close from CSV (bootstrap-only, only once)
    load_etf_prev_close_from_csv()
    
    if static_store is None:
        static_store = StaticDataStore()
        # Sync with global instance in static_data_store module
        from app.market_data.static_data_store import initialize_static_store
        initialize_static_store()
        # Auto-load CSV if configured (default: True)
        if settings.AUTO_LOAD_CSV:
            logger.info("📊 AUTO_LOAD_CSV enabled - loading CSV automatically on startup...")
            success = static_store.load_csv()
            if success:
                symbol_count = len(static_store.get_all_symbols())
                logger.info(f"✅ CSV loaded successfully: {symbol_count} symbols (startup auto-load)")
            else:
                logger.warning("⚠️ CSV auto-load failed. Use /api/market-data/load-csv endpoint to load manually.")
        else:
            logger.info("ℹ️ AUTO_LOAD_CSV disabled - CSV not loaded on startup (set AUTO_LOAD_CSV=true to enable)")
    if metrics_engine is None:
        metrics_engine = DerivedMetricsEngine()
    if janall_metrics_engine is None:
        janall_metrics_engine = JanallMetricsEngine()
    if benchmark_engine is None:
        from app.market_data.benchmark_engine import get_benchmark_engine
        benchmark_engine = get_benchmark_engine()
    if state_engine is None:
        state_engine = SymbolStateEngine()
    if intent_engine is None:
        intent_engine = IntentEngine()
    if order_planner is None:
        order_planner = OrderPlanner()
    if order_queue is None:
        order_queue = OrderQueue()
    if order_gate is None:
        order_gate = OrderGate()
    if user_action_store is None:
        user_action_store = UserActionStore()
    if signal_interpreter is None:
        signal_interpreter = SignalInterpreter()
    if rank_engine is None:
        rank_engine = RankEngine()
    if grpan_engine is None:
        # Initialize GRPANEngine with 300ms compute interval (250-500ms range)
        grpan_engine = GRPANEngine(compute_interval_ms=300.0)
        # Sync with global instance in grpan_engine module
        from app.market_data.grpan_engine import initialize_grpan_engine
        initialize_grpan_engine()
    
    # Initialize RWVAPEngine (uses GRPANEngine's extended_prints_store and last_price_cache)
    global rwvap_engine
    if rwvap_engine is None:
        rwvap_engine = initialize_rwvap_engine(
            extended_prints_store=grpan_engine.extended_prints_store,
            static_store=static_store,
            extreme_multiplier=1.0  # AVG_ADV * 1.0 threshold (exclude prints >= AVG_ADV)
        )
        # Set last_price_cache reference for consistent "last" price across all windows
        rwvap_engine.set_last_price_cache(grpan_engine.last_price_cache)
        logger.info("RWVAPEngine initialized (extreme_multiplier=1.0)")
    
    # Initialize TradePrintRouter (normalizes trade prints, routes to GRPANEngine)
    global trade_print_router
    if trade_print_router is None and TradePrintRouter is not None:
        trade_print_router = TradePrintRouter(grpan_engine)
        logger.info("TradePrintRouter initialized")
    elif TradePrintRouter is None:
        logger.warning("TradePrintRouter class not available, trade prints will not be routed")
    
    # Initialize GRPANTickFetcher (bootstrap/recovery mode - only fetches when needed)
    # 🔵 CRITICAL: GRPANTickFetcher is now ONLY handled by worker process
    # Backend does NOT start GRPANTickFetcher to avoid blocking terminal
    # Worker (deeper_analysis_worker.py) has its own GRPANTickFetcher instance
    global grpan_tick_fetcher
    # Keep as None - worker will handle all GRPAN bootstrap
    grpan_tick_fetcher = None
    logger.info("🔵 SLOW PATH: GRPANTickFetcher DISABLED in backend (handled by worker process)")
    if position_analytics_engine is None:
        position_analytics_engine = PositionAnalyticsEngine()
    if exposure_mode_engine is None:
        exposure_mode_engine = ExposureModeEngine()
    if position_snapshot_engine is None:
        position_snapshot_engine = PositionSnapshotEngine()
        
    # Trigger initial FAST score computation (L1 + CSV + Group Metrics)
    # This prepares fbtot/sfstot/gort which are required for RunAll pre-flight check
    try:
        from app.core.fast_score_calculator import compute_all_fast_scores
        logger.info("🚀 Triggering initial FAST score computation...")
        compute_all_fast_scores(include_group_metrics=True)
    except Exception as e:
        logger.warning(f"⚠️ Initial FAST score computation failed: {e}")

    if position_guard_engine is None:
        position_guard_engine = PositionGuardEngine()
    if psfalgo_action_planner is None:
        psfalgo_action_planner = PSFALGOActionPlanner()
    if execution_router is None:
        execution_router = ExecutionRouter(ExecutionMode.PREVIEW)
    
    # Initialize PricingOverlayEngine
    global pricing_overlay_engine
    if pricing_overlay_engine is None:
        pricing_overlay_engine = PricingOverlayEngine(
            config={
                'min_interval_ms': 250,
                'batch_size': 200,
                'max_queue_size': 500
            }
        )
        # Sync with global instance in pricing_overlay_engine module
        from app.market_data.pricing_overlay_engine import initialize_pricing_overlay_engine
        initialize_pricing_overlay_engine(config={
            'min_interval_ms': 250,
            'batch_size': 200,
            'max_queue_size': 500
        })
        logger.info("PricingOverlayEngine initialized")
    
    # Mark as initialized (prevent future initialization)
    _market_data_services_initialized = True
    logger.info("Market data services initialized (startup-only)")


def update_market_data_cache(symbol: str, data: Dict[str, Any]):
    """
    Update market data cache (called by Hammer feed)
    
    Args:
        symbol: Symbol (PREF_IBKR)
        data: Market data from Hammer L1Update (bid, ask, last, but NOT prev_close)
    
    Note:
        prev_close MUST come from getSymbolSnapshot (L1Update does NOT contain prevClose).
        
        CRITICAL: Snapshot fetch NEVER happens in L1Update path (real-time blocking).
        Instead, snapshot is fetched asynchronously via snapshot queue:
        - If prev_close is missing, enqueue snapshot request (non-blocking)
        - Snapshot worker processes requests in background (rate-limited, max 2/sec)
        - Failed snapshots are cached (5 min TTL) to prevent retry spam
        
        CSV fallback is removed - Hammer is the single source of truth for prev_close.
        Hammer's prevClose is dividend/split adjusted automatically (e.g., NTRSO ex-div adjustment).
    """
    global market_data_cache, pricing_overlay_engine
    
    # L1Update does NOT contain prevClose - we must get it from getSymbolSnapshot
    prev_close = data.get('prev_close')
    
    # CRITICAL: If prev_close is missing, try to get it from CSV (DataFabric/StaticDataStore)
    # This ensures MarketSnapshotStore has prev_close for DataReadinessChecker
    if not prev_close or prev_close <= 0:
        try:
            # Try DataFabric first (fastest - already in RAM)
            from app.core.data_fabric import get_data_fabric
            fabric = get_data_fabric()
            if fabric:
                static_data = fabric.get_static(symbol)
                if static_data and static_data.get('prev_close'):
                    prev_close = static_data.get('prev_close')
                    data['prev_close'] = prev_close
                    logger.debug(f"📊 {symbol}: Using prev_close={prev_close} from DataFabric")
        except Exception:
            pass
        
        # Fallback: Try StaticDataStore
        if not prev_close or prev_close <= 0:
            try:
                from app.market_data.static_data_store import get_static_store
                static_store_local = get_static_store()
                if static_store_local:
                    static_data = static_store_local.get_static_data(symbol)
                    if static_data and static_data.get('prev_close'):
                        prev_close_val = static_data.get('prev_close')
                        try:
                            prev_close = float(prev_close_val)
                            if prev_close > 0:
                                data['prev_close'] = prev_close
                                logger.debug(f"📊 {symbol}: Using prev_close={prev_close} from StaticDataStore")
                        except (ValueError, TypeError):
                            pass
            except Exception:
                pass
    
    # CRITICAL: Snapshot is BOOTSTRAP-ONLY, NOT real-time
    # Snapshot fetch is removed from L1Update path
    # prev_close comes from:
    #   - CSV (for preferred stocks) - loaded at startup
    #   - Hammer snapshot (for ETF + benchmark only) - fetched at startup
    #   - State-based snapshot (one-time fetch, never retried from L1Update)
    
    # If prev_close is missing, it will be:
    #   1. Loaded from CSV (if available)
    #   2. Fetched via snapshot state manager (bootstrap-only, not from L1Update)
    #   3. NOT fetched from L1Update path (prev_close is not real-time data)
    
    # Store in cache (with prev_close from CSV if available)
    market_data_cache[symbol] = data
    
    # EVENT-DRIVEN: For preferred stocks, send update immediately (bypass broadcast loop)
    # This restores the old "instant fill" behavior where each L1Update triggers immediate UI update
    # ETFs will still use the broadcast loop (they can be batched)
    global _dirty_symbols  # Declare global at the start
    
    if symbol not in ETF_TICKERS:
        # Preferred stock - send immediately via WebSocket (event-driven)
        # Use thread-safe asyncio to send from sync context (Hammer feed thread) to async context
        try:
            from app.api.websocket_routes import get_connection_manager
            connection_manager = get_connection_manager()
            if connection_manager and connection_manager.active_connections:
                # Build update message for this single symbol
                # Calculate spread if not provided (ask - bid)
                spread = data.get('spread')
                if spread is None:
                    bid = data.get('bid')
                    ask = data.get('ask')
                    if bid is not None and ask is not None:
                        spread = ask - bid
                
                update_message = {
                    'PREF_IBKR': symbol,
                    'bid': data.get('bid'),
                    'ask': data.get('ask'),
                    'last': data.get('last') or data.get('price'),
                    'prev_close': data.get('prev_close'),
                    'spread': spread,
                    'volume': data.get('volume')
                }
                
                # Add calculated metrics (GORT, FBTOT, SFSTOT) if available from JanallMetricsEngine
                # These are computed in batch, so may not be available for every L1Update
                try:
                    if janall_metrics_engine and hasattr(janall_metrics_engine, 'symbol_metrics_cache'):
                        janall_metrics = janall_metrics_engine.symbol_metrics_cache.get(symbol, {})
                        if janall_metrics:
                            # Add metrics if available (None if not computed yet)
                            update_message['GORT'] = janall_metrics.get('gort')
                            update_message['Fbtot'] = janall_metrics.get('fbtot')
                            update_message['SFStot'] = janall_metrics.get('sfstot')
                except Exception as e:
                    # Non-critical - metrics may not be computed yet
                    logger.debug(f"Could not get Janall metrics for {symbol} in WebSocket update: {e}")
                
                # Thread-safe async call: schedule broadcast on main event loop
                # This works even if called from Hammer feed thread
                import asyncio
                try:
                    # Get the main event loop (FastAPI's loop)
                    # Use get_event_loop() which works from any thread
                    loop = asyncio.get_event_loop()
                    # Schedule broadcast on the main event loop (thread-safe)
                    asyncio.run_coroutine_threadsafe(
                        connection_manager.broadcast({
                            "type": "market_data_update",
                            "data": [update_message]  # Single symbol update
                        }),
                        loop
                    )
                except (RuntimeError, AttributeError):
                    # No event loop available - mark as dirty for broadcast loop fallback
                    _dirty_symbols.add(symbol)
        except Exception as e:
            # Non-critical - if WebSocket fails, broadcast loop will catch it
            logger.debug(f"Immediate broadcast failed for {symbol}, using dirty queue: {e}")
            _dirty_symbols.add(symbol)
    else:
        # ETF - mark as dirty for broadcast loop (batched updates are OK for ETFs)
        _dirty_symbols.add(symbol)
    
    # Mark symbol as dirty for pricing overlay engine
    if pricing_overlay_engine:
        pricing_overlay_engine.mark_dirty(symbol)
    
    # NOTE: MarketSnapshotStore will be updated by:
    # 1. WebSocket broadcast loop (periodic updates for dirty symbols)
    # 2. /api/market-data/merged endpoint (when called)
    # 3. /api/psfalgo/scanner endpoint (on-demand, reads from market_data_cache if MarketSnapshotStore is empty)
    # This ensures UI always sees bid/ask/last updates in real-time
    
    # 🟢 CRITICAL: Update DataFabric (Single Source of Truth)
    # This ensures FastScoreCalculator and RunallEngine see the data
    try:
        from app.core.data_fabric import get_data_fabric
        fabric = get_data_fabric()
        if fabric:
            fabric.update_live(symbol, data)
    except Exception as e:
        logger.error(f"Failed to update DataFabric for {symbol}: {e}")

    # Log first few cache updates to verify BID/ASK are being stored
    if not hasattr(update_market_data_cache, '_cache_log_count'):
        update_market_data_cache._cache_log_count = 0
    update_market_data_cache._cache_log_count += 1
    if update_market_data_cache._cache_log_count <= 5:
        logger.info(f"📊 Cache update #{update_market_data_cache._cache_log_count}: {symbol} bid={data.get('bid')} ask={data.get('ask')} last={data.get('last')} (dirty_symbols={len(_dirty_symbols)})")
    else:
        logger.debug(f"Market data cache updated for {symbol} (prev_close={prev_close})")


def update_etf_market_data(symbol: str, data: Dict[str, Any]):
    """
    Update ETF market data store (called by Hammer feed for ETF tickers)
    
    Args:
        symbol: ETF symbol (e.g., 'TLT', 'SPY')
        data: Market data from Hammer L1Update (bid, ask, last, but NOT prev_close)
    
    Note:
        prev_close MUST come from getSymbolSnapshot (L1Update does NOT contain prevClose).
        
        CRITICAL: Snapshot fetch NEVER happens in L1Update path (real-time blocking).
        Instead, snapshot is fetched asynchronously via snapshot queue:
        - If prev_close is missing, enqueue snapshot request (non-blocking)
        - Snapshot worker processes requests in background (rate-limited, max 2/sec)
        - Failed snapshots are cached (5 min TTL) to prevent retry spam
        
        CSV fallback is removed - Hammer is the single source of truth for prev_close.
        Hammer's prevClose is dividend/split adjusted automatically.
    """
    global etf_market_data, etf_prev_close, pricing_overlay_engine
    
    # Get last price from L1Update
    last = data.get('last') or data.get('price')
    
    prev_close = data.get('prev_close')  # L1Update does NOT contain prevClose
    
    # CRITICAL: Snapshot is BOOTSTRAP-ONLY, NOT real-time
    # ETF prev_close comes from:
    #   - CSV (janeketfs.csv) - PRIMARY SOURCE (loaded at startup)
    #   - NOT from Hammer snapshot (CSV is the single source of truth)
    #   - NOT from L1Update path (prev_close is not real-time data)
    
    # If prev_close is missing from L1Update data, try to get it from CSV cache
    if not prev_close or prev_close <= 0:
        # Try to get from CSV cache (loaded at startup)
        prev_close = etf_prev_close.get(symbol)
        if prev_close and prev_close > 0:

            # Update data with CSV prev_close
            data['prev_close'] = prev_close
            
            # 🟢 CRITICAL: Update DataFabric ETF data
            try:
                from app.core.data_fabric import get_data_fabric
                fabric = get_data_fabric()
                if fabric:
                    fabric.update_etf_live(symbol, data)
                    fabric.set_etf_prev_close(symbol, prev_close)
            except Exception as e:
                logger.error(f"Failed to update DataFabric ETF for {symbol}: {e}")

            # Reduce logging - only log first few ETF updates per symbol
            if not hasattr(update_etf_market_data, '_etf_log_count'):
                update_etf_market_data._etf_log_count = {}
            if symbol not in update_etf_market_data._etf_log_count:
                update_etf_market_data._etf_log_count[symbol] = 0
            update_etf_market_data._etf_log_count[symbol] += 1
            if update_etf_market_data._etf_log_count[symbol] <= 3:
                logger.info(f"📊 ETF {symbol}: Using prev_close={prev_close} from CSV cache (last={last})")
            else:
                logger.debug(f"📊 ETF {symbol}: Using prev_close={prev_close} from CSV cache (last={last})")
        else:
            # Log available keys for debugging
            available_keys = list(etf_prev_close.keys())
            logger.warning(f"⚠️ ETF {symbol}: prev_close not found in CSV cache. Available keys: {available_keys}")
    
    # Store ETF market data
    etf_market_data[symbol] = data
    
    # Mark symbol as dirty for WebSocket broadcast (optimization: only send changed symbols)
    global _dirty_symbols
    _dirty_symbols.add(symbol)
    
    # Mark symbol as dirty for pricing overlay engine
    if pricing_overlay_engine:
        pricing_overlay_engine.mark_dirty(symbol)
    
    # Cache prev_close for later use (if available)
    if prev_close and prev_close > 0:
        etf_prev_close[symbol] = prev_close
    
    # NOTE: MarketSnapshotStore will be updated by:
    # 1. WebSocket broadcast loop (periodic updates for dirty symbols)
    # 2. /api/market-data/merged endpoint (when called)
    # 3. /api/psfalgo/scanner endpoint (on-demand, reads from market_data_cache if MarketSnapshotStore is empty)
    # This ensures UI always sees bid/ask/last updates in real-time
    
    # Calculate daily change
    daily_change_percent = None
    daily_change_cents = None
    
    if last is not None and prev_close is not None and prev_close > 0:
        daily_change_cents = last - prev_close
        daily_change_percent = (daily_change_cents / prev_close) * 100
        
        # Mark benchmark dirty for pricing overlay engine (when ETF price changes)
        if pricing_overlay_engine:
            pricing_overlay_engine.mark_benchmark_dirty(symbol)
    
    # Update ETF market data dict with calculated values (merge with existing data)
    etf_market_data[symbol].update({
        'symbol': symbol,
        'last': last,
        'prev_close': prev_close,
        'daily_change_percent': daily_change_percent,
        'daily_change_cents': daily_change_cents,
        'timestamp': data.get('timestamp')
    })
    
    # Debug: Log ETF updates (after daily_change_percent is calculated)
    logger.debug(f"📊 ETF update: {symbol} last={last} prev_close={prev_close} daily_change_percent={daily_change_percent}")
    
    # Mark benchmark dirty for pricing overlay engine (when ETF price changes)
    if pricing_overlay_engine and last is not None:
        pricing_overlay_engine.mark_benchmark_dirty(symbol)
    
    # Safe logging (avoid formatting None)
    try:
        logger.debug(
            f"ETF market data updated for {symbol}: "
            f"last={last if last is not None else 'N/A'}, "
            f"prev_close={prev_close if prev_close is not None else 'N/A'}, "
            f"chg_pct={daily_change_percent if daily_change_percent is not None else 'N/A'}"
        )
    except Exception:
        pass


def get_etf_market_data() -> Dict[str, Dict[str, Any]]:
    """Get all ETF market data"""
    global etf_market_data
    return etf_market_data.copy()


def get_janall_metrics_engine() -> Optional[JanallMetricsEngine]:
    """Get Janall metrics engine instance"""
    global janall_metrics_engine
    return janall_metrics_engine


def get_rank_engine() -> Optional[RankEngine]:
    """Get rank engine instance"""
    global rank_engine
    return rank_engine

def get_grpan_engine() -> Optional[GRPANEngine]:
    """Get GRPAN engine instance"""
    global grpan_engine
    return grpan_engine

def get_trade_print_router() -> Optional[TradePrintRouter]:
    """Get TradePrintRouter instance"""
    global trade_print_router
    return trade_print_router

def get_position_analytics_engine() -> Optional[PositionAnalyticsEngine]:
    """Get Position Analytics engine instance"""
    global position_analytics_engine
    return position_analytics_engine

def get_exposure_mode_engine() -> Optional[ExposureModeEngine]:
    """Get Exposure Mode engine instance"""
    global exposure_mode_engine
    return exposure_mode_engine

def get_position_snapshot_engine() -> Optional[PositionSnapshotEngine]:
    """Get Position Snapshot engine instance"""
    global position_snapshot_engine
    return position_snapshot_engine

def get_position_guard_engine() -> Optional[PositionGuardEngine]:
    """Get Position Guard engine instance"""
    global position_guard_engine
    return position_guard_engine

def get_psfalgo_action_planner() -> Optional[PSFALGOActionPlanner]:
    """Get PSFALGO Action Planner instance"""
    global psfalgo_action_planner
    return psfalgo_action_planner


def get_benchmark_engine() -> Optional[BenchmarkEngine]:
    """Get benchmark engine instance"""
    global benchmark_engine
    return benchmark_engine

def get_pricing_overlay_engine():
    """Get pricing overlay engine instance"""
    global pricing_overlay_engine
    return pricing_overlay_engine

def get_etf_prev_close():
    """Get ETF prev_close dict"""
    global etf_prev_close
    return etf_prev_close


def get_dirty_symbols() -> set:
    """
    Get set of symbols that have been updated since last broadcast.
    Used for WebSocket optimization (only broadcast changed symbols).
    
    Returns:
        set: Set of dirty symbol names
    """
    global _dirty_symbols
    return _dirty_symbols.copy()


def clear_dirty_symbols():
    """
    Clear dirty symbols set (called after WebSocket broadcast).
    Used for WebSocket optimization.
    """
    global _dirty_symbols
    _dirty_symbols.clear()


@router.get("/live-view-stats")
async def get_live_view_stats():
    """
    Get live view statistics for UI status display.
    
    Returns:
        Dict with live_data and algo_ready status
    """
    try:
        from app.market_data.live_view_service import get_live_view_service
        
        live_view = get_live_view_service()
        if not live_view:
            return {
                "success": False,
                "error": "LiveViewService not initialized"
            }
        
        stats = live_view.get_live_view_stats()
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Error getting live view stats: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/merged")
async def get_merged_market_data():
    """
    Get merged data: static CSV + live Hammer market data + derived scores
    
    Returns:
        List of merged records with static fields, live fields, and derived scores
    """
    try:
        # Services already initialized at startup (no CSV reload on request)
        if not static_store or not static_store.is_loaded():
            raise HTTPException(
                status_code=404,
                detail="Static data not loaded. Please load janalldata.csv first."
            )
        
        symbols = static_store.get_all_symbols()
        if not symbols:
            return {"success": True, "data": [], "count": 0}
        
        # Batch compute Janall metrics (every 2 seconds, cached)
        if janall_metrics_engine and benchmark_engine:
            try:
                etf_data = get_etf_market_data()
                janall_metrics_engine.compute_batch_metrics(
                    symbols, static_store, market_data_cache, etf_data
                )
                logger.debug(f"Janall batch metrics computed for {len(symbols)} symbols")
                
                # CRITICAL: Update MarketSnapshotStore with computed metrics
                # This ensures FBTOT, SFSTOT, GORT, FINAL_* scores are available in scanner
                try:
                    from app.psfalgo.metric_compute_engine import get_metric_compute_engine
                    from app.psfalgo.market_snapshot_store import get_market_snapshot_store
                    from app.psfalgo.account_mode import get_account_mode_manager
                    
                    metric_engine = get_metric_compute_engine()
                    snapshot_store = get_market_snapshot_store()
                    account_mode_manager = get_account_mode_manager()
                    
                    if metric_engine and snapshot_store:
                        # Get current account type
                        account_type = 'IBKR_GUN'  # Default
                        if account_mode_manager:
                            current_mode = account_mode_manager.get_mode()
                            if current_mode == 'IBKR_GUN':
                                account_type = 'IBKR_GUN'
                            elif current_mode == 'IBKR_PED':
                                account_type = 'IBKR_PED'
                            else:
                                account_type = 'IBKR_GUN'  # Default for HAMMER_PRO
                        
                        # Update MarketSnapshot for each symbol with computed metrics
                        # CRITICAL: Each symbol must be processed independently - one failure should not stop others
                        updated_count = 0
                        failed_count = 0
                        for symbol in symbols:
                            try:
                                static_data = static_store.get_static_data(symbol)
                                if not static_data:
                                    continue
                                
                                market_data = market_data_cache.get(symbol, {})
                                if not market_data:
                                    continue
                                
                                # Get Janall metrics from cache (fbtot, sfstot, gort)
                                janall_metrics = None
                                if janall_metrics_engine and hasattr(janall_metrics_engine, 'symbol_metrics_cache'):
                                    janall_metrics = janall_metrics_engine.symbol_metrics_cache.get(symbol, {})
                                
                                # Compute metrics (will use FBTOT/SFSTOT/GORT from JanallMetricsEngine cache)
                                snapshot = metric_engine.compute_metrics(
                                    symbol=symbol,
                                    market_data=market_data,
                                    position_data=None,  # Position data optional for scanner
                                    static_data=static_data,
                                    janall_metrics=janall_metrics  # Pass Janall metrics explicitly
                                )
                                
                                # Update MarketSnapshotStore (async)
                                await snapshot_store.update_current_snapshot(symbol, snapshot, account_type=account_type)
                                updated_count += 1
                            except Exception as e:
                                failed_count += 1
                                logger.debug(f"[METRIC] Failed to update MarketSnapshot for {symbol}: {e}")
                                # Continue with next symbol - DO NOT break the loop
                        
                        if updated_count > 0:
                            # Sample a few symbols to verify metrics are populated
                            sample_symbols = list(symbols)[:5] if symbols else []
                            sample_info = []
                            for sym in sample_symbols:
                                snapshot = snapshot_store.get_current_snapshot(sym, account_type=account_type)
                                if snapshot:
                                    sample_info.append(f"{sym}: fbtot={snapshot.fbtot}, gort={snapshot.gort}, sfstot={snapshot.sfstot}")
                            if sample_info:
                                logger.info(f"[METRIC] Updated {updated_count} MarketSnapshots (failed: {failed_count}). Samples: {' | '.join(sample_info)}")
                            else:
                                logger.debug(f"[METRIC] Updated {updated_count} MarketSnapshots with computed metrics (FBTOT/SFSTOT/GORT) (failed: {failed_count})")
                except Exception as e:
                    logger.warning(f"[METRIC] Error updating MarketSnapshotStore: {e}", exc_info=True)
            except Exception as e:
                logger.warning(f"Error in Janall batch metrics: {e}")
        
        # Batch compute GRPAN metrics
        if grpan_engine:
            try:
                grpan_engine.compute_batch_grpan(symbols)
                logger.debug(f"GRPAN batch metrics computed for {len(symbols)} symbols")
            except Exception as e:
                logger.warning(f"Error in GRPAN batch metrics: {e}")
        
        # Batch fetch positions and orders ONCE (O(1) API calls per cycle)
        positions_cache = []
        orders_cache = []
        if position_snapshot_engine:
            try:
                # PHASE 10: Check account mode - IBKR or HAMMER
                from app.psfalgo.account_mode import get_account_mode_manager
                from app.api.trading_routes import get_hammer_positions_service, get_hammer_orders_service
                
                account_mode_manager = get_account_mode_manager()
                
                if account_mode_manager and account_mode_manager.is_ibkr():
                    # IBKR mode: Get positions from IBKR
                    from app.psfalgo.ibkr_connector import get_ibkr_connector
                    from app.psfalgo.position_snapshot_api import get_position_snapshot_api
                    
                    account_type = account_mode_manager.get_account_type()
                    ibkr_connector = get_ibkr_connector(account_type=account_type)
                    
                    if ibkr_connector and ibkr_connector.is_connected():
                        # Get positions from IBKR
                        ibkr_positions = await ibkr_connector.get_positions()
                        # Convert to format expected by merged data
                        positions_cache = [
                            {
                                'symbol': p.get('symbol'),
                                'qty': p.get('qty', 0.0),
                                'avg_price': p.get('avg_price', 0.0),
                                'account': p.get('account', account_type)
                            }
                            for p in ibkr_positions
                        ]
                        logger.debug(f"Fetched {len(positions_cache)} positions from IBKR {account_type} for batch processing")
                        
                        # Get orders from IBKR
                        ibkr_orders = await ibkr_connector.get_open_orders()
                        orders_cache = [
                            {
                                'symbol': o.get('symbol'),
                                'side': o.get('side'),
                                'qty': o.get('qty', 0.0),
                                'order_type': o.get('order_type'),
                                'limit_price': o.get('limit_price'),
                                'status': o.get('status', 'OPEN'),
                                'account': o.get('account', account_type)
                            }
                            for o in ibkr_orders if o.get('status', '').upper() == 'OPEN'
                        ]
                        logger.debug(f"Fetched {len(orders_cache)} open orders from IBKR {account_type} for batch processing")
                    else:
                        logger.debug(f"IBKR {account_type} not connected, skipping positions/orders")
                else:
                    # HAMMER mode: Get positions from Hammer
                    positions_service = get_hammer_positions_service()
                    if positions_service:
                        positions_cache = positions_service.get_positions(force_refresh=False)
                        logger.debug(f"Fetched {len(positions_cache)} positions from Hammer for batch processing")
                    
                    orders_service = get_hammer_orders_service()
                    if orders_service:
                        all_orders = orders_service.get_orders(force_refresh=False)
                        # Filter for OPEN orders only
                        orders_cache = [o for o in all_orders if o.get('status', '').upper() == 'OPEN']
                        logger.debug(f"Fetched {len(orders_cache)} open orders from Hammer for batch processing")
            except Exception as e:
                logger.warning(f"Error fetching positions/orders for batch: {e}")
        
        merged_data = []
        
        logger.info(f"Processing {len(symbols)} symbols for merged data")
        
        # Process pricing overlay dirty queue before building merged data
        # This ensures overlay scores are computed if market data is available
        if pricing_overlay_engine and static_store and static_store.is_loaded():
            try:
                etf_market_data = get_etf_market_data()
                computed_results = pricing_overlay_engine.process_dirty_queue(
                    static_store=static_store,
                    market_data_cache=market_data_cache,
                    etf_market_data=etf_market_data,
                    etf_prev_close=etf_prev_close
                )
                if computed_results:
                    # Debug: Check how many have benchmark_chg
                    with_benchmark = sum(1 for r in computed_results.values() if r.get('benchmark_chg') is not None)
                    collecting = sum(1 for r in computed_results.values() if r.get('status') == 'COLLECTING')
                    logger.info(f"[PRICING_OVERLAY] Processed {len(computed_results)} overlay scores: {with_benchmark} with benchmark_chg, {collecting} COLLECTING")
                else:
                    logger.debug(f"[PRICING_OVERLAY] No overlay scores computed. ETF data: {len(etf_market_data)} ETFs, prev_close: {len(etf_prev_close)} ETFs")
            except Exception as e:
                logger.warning(f"Error processing pricing overlay queue in merged endpoint: {e}")
        
        for symbol in symbols:
            # Get static data
            static_data = static_store.get_static_data(symbol)
            if not static_data:
                continue
            
            # Get live market data (must include prev_close from Hammer)
            market_data = market_data_cache.get(symbol, {})
            # Always include the record even if market data is not available yet
            # Use empty market data if not available
            if not market_data:
                market_data = {
                    'bid': None,
                    'ask': None,
                    'last': None,
                    'price': None,
                    'spread': None,
                    'volume': None,
                    'prev_close': None
                }
            
            # CRITICAL: prev_close MUST come from Hammer getSymbolSnapshot, NOT from CSV
            # CSV fallback removed - Hammer is the single source of truth (dividend/split adjusted)
            # NOTE: We do NOT fetch snapshot here in get_merged_market_data - too many API calls
            # Snapshot is fetched lazily in update_market_data_cache() when L1Update arrives
            # If prev_close is missing here, it means snapshot hasn't been fetched yet (normal)
            # UI will show N/A until L1Update triggers snapshot fetch
            
            # Calculate spread if not provided
            bid = market_data.get('bid')
            ask = market_data.get('ask')
            if market_data.get('spread') is None:
                if bid and ask and bid > 0 and ask > 0:
                    market_data['spread'] = ask - bid
                else:
                    market_data['spread'] = 0.0
            
            # Calculate spread_percent
            spread_percent = None
            bid = market_data.get('bid')
            ask = market_data.get('ask')
            if bid and ask and bid > 0 and ask > 0:
                spread = ask - bid
                mid_price = (bid + ask) / 2
                if mid_price > 0:
                    spread_percent = (spread / mid_price) * 100
            
            # Get Janall metrics from cached batch results
            janall_metrics = {}
            if janall_metrics_engine and hasattr(janall_metrics_engine, 'symbol_metrics_cache'):
                janall_metrics = janall_metrics_engine.symbol_metrics_cache.get(symbol, {})
            
            # Get GRPAN metrics (latest_pan for backward compatibility)
            grpan_metrics = {}
            grpan_all_windows = {}
            if grpan_engine:
                grpan_metrics = grpan_engine.get_grpan_for_symbol(symbol)
                # Get all windows for GOD calculation and PAN display
                grpan_all_windows = grpan_engine.get_all_windows_for_symbol(symbol)
            
            # Get RWVAP windows for ROD calculation
            rwvap_windows_data = {}
            if rwvap_engine:
                rwvap_windows_data = rwvap_engine.get_all_rwvap_for_symbol(symbol) or {}
            
            # Compute symbol state, reason, and transition
            state = 'IDLE'  # Default
            state_reason = {}
            transition_reason = {}
            if state_engine:
                state, state_reason, transition_reason = state_engine.compute_state(symbol, static_data, market_data)
            
            # Compute intent
            intent = 'WAIT'  # Default
            intent_reason = {}
            if intent_engine:
                intent, intent_reason = intent_engine.compute_intent(state, market_data, static_data)
            
            # Plan order (dry-run, no execution)
            order_plan = {}
            if order_planner:
                order_plan = order_planner.plan_order(intent, intent_reason, market_data, static_data, grpan_metrics)
                # Add symbol and intent to order plan for execution and gate evaluation
                order_plan['symbol'] = symbol
                order_plan['intent'] = intent  # Add intent for GRPAN filter in OrderGate
            
            # Queue order (simulation-only)
            queue_status = {}
            if order_queue and order_plan.get('action') != 'NONE':
                queue_status = order_queue.enqueue_order(symbol, order_plan)
            elif order_plan.get('action') == 'NONE':
                # Get queue info even if not queued
                if order_queue:
                    queue_status = order_queue.get_queue_info_for_symbol(symbol)
            
            # Evaluate order gate (pre-execution safety layer)
            # Add GRPAN metrics to market_data for gate evaluation
            if grpan_metrics:
                market_data['grpan_concentration_percent'] = grpan_metrics.get('concentration_percent')
                market_data['grpan_print_count'] = grpan_metrics.get('print_count', 0)
                market_data['grpan_real_lot_count'] = grpan_metrics.get('real_lot_count', 0)
                market_data['grpan_price'] = grpan_metrics.get('grpan_price')
            
            gate_status = {}
            if order_gate:
                gate_status = order_gate.evaluate_gate(order_plan, queue_status, market_data, static_data)
            
            # Get user action (if any)
            user_action_data = {}
            user_action_value = None
            if user_action_store:
                user_action_record = user_action_store.get_user_action(symbol)
                if user_action_record:
                    user_action_value = user_action_record.get('user_action')
                    user_action_data = {
                        'user_action': user_action_value,
                        'user_note': user_action_record.get('user_note'),
                        'timestamp': user_action_record.get('timestamp')
                    }
            
            # Execution routing REMOVED - all orders must go through Intent system
            # ExecutionRouter now only handles APPROVED intents (via /api/psfalgo/intents/{id}/approve)
            execution_result = {
                'execution_status': 'SKIPPED_NO_INTENT',
                'execution_reason': 'Direct execution disabled - use Intent system',
                'execution_mode': 'PREVIEW'
            }
            
            # Compute ranks for Fbtot and SFStot
            rank_data = {}
            if rank_engine and janall_metrics_engine and hasattr(janall_metrics_engine, 'group_stats_cache'):
                rank_data = rank_engine.compute_ranks(
                    symbol, janall_metrics, janall_metrics_engine.group_stats_cache
                )
            
            # Interpret signal from Janall metrics
            signal_data = {}
            if signal_interpreter:
                # Build temporary merged record for signal interpreter
                temp_merged = {
                    'Fbtot': janall_metrics.get('fbtot'),
                    'SFStot': janall_metrics.get('sfstot'),
                    'GORT': janall_metrics.get('gort'),
                    'FinalFB': janall_metrics.get('final_fb'),
                    'FinalSFS': janall_metrics.get('final_sfs'),
                    'AVG_ADV': static_data.get('AVG_ADV'),
                    'benchmark_chg': janall_metrics.get('benchmark_chg'),
                    'fbtot_rank_norm': rank_data.get('fbtot_rank_norm'),  # Pass normalized rank
                    'sfstot_rank_norm': rank_data.get('sfstot_rank_norm')  # Pass normalized rank
                }
                signal_data = signal_interpreter.interpret_signal(temp_merged)
            
            # Compute position analytics
            position_analytics = {}
            if position_analytics_engine:
                position_analytics = position_analytics_engine.compute_position_analytics(
                    symbol, static_data, market_data, order_plan
                )
            
            # Compute exposure mode
            exposure_mode = {}
            if exposure_mode_engine:
                exposure_mode = exposure_mode_engine.compute_exposure_mode(
                    symbol, market_data, static_data, signal_data, grpan_metrics, position_analytics
                )
            
            # Compute PSFALGO position snapshot
            # Use batch-fetched positions and orders cache (O(1) API calls per cycle)
            psfalgo_snapshot = {}
            if position_snapshot_engine:
                psfalgo_snapshot = position_snapshot_engine.compute_snapshot(
                    symbol, static_data, market_data,
                    positions_cache=positions_cache,
                    orders_cache=orders_cache
                )
            
            # Evaluate PSFALGO guards
            psfalgo_guards = {}
            if position_guard_engine and psfalgo_snapshot:
                psfalgo_guards = position_guard_engine.evaluate_guards(
                    symbol, psfalgo_snapshot, static_data, order_plan
                )
                # Fill in guard_reason inputs
                if 'guard_reason' in psfalgo_guards and 'inputs' in psfalgo_guards['guard_reason']:
                    psfalgo_guards['guard_reason']['inputs']['current_qty'] = psfalgo_snapshot.get('current_qty')
                    psfalgo_guards['guard_reason']['inputs']['potential_qty'] = psfalgo_snapshot.get('potential_qty')
            
            # Compute PSFALGO action plan
            psfalgo_action_plan = {}
            if psfalgo_action_planner and psfalgo_snapshot and psfalgo_guards:
                psfalgo_action_plan = psfalgo_action_planner.plan_action(
                    symbol, psfalgo_snapshot, psfalgo_guards, janall_metrics, exposure_mode
                )
            
            # Calculate MAXALW = AVG_ADV / 10 (static data)
            avg_adv = static_data.get('AVG_ADV')
            maxalw = None
            if avg_adv is not None:
                try:
                    avg_adv_float = float(avg_adv)
                    if avg_adv_float > 0:
                        maxalw = int(avg_adv_float / 10)
                except (ValueError, TypeError):
                    pass
            
            # Get benchmark type from CGRUP (Janall logic: CGRUP varsa CGRUP, yoksa DEFAULT)
            # This MUST match the benchmark_rules.yaml keys exactly
            cgrup = static_data.get('CGRUP') or static_data.get('cgrup')
            benchmark_type = 'DEFAULT'
            if cgrup:
                try:
                    cgrup_str = str(cgrup).strip()
                    if cgrup_str and cgrup_str.lower() != 'nan' and cgrup_str.lower() != '':
                        if cgrup_str.lower().startswith('c'):
                            # Already in C525 format
                            benchmark_type = cgrup_str.upper()  # 'c525' -> 'C525'
                        else:
                            # Eski format: sayısal değer (5.25 -> C525)
                            try:
                                numeric_value = float(cgrup_str)
                                benchmark_type = f"C{int(numeric_value * 100)}"
                            except (ValueError, TypeError):
                                benchmark_type = 'DEFAULT'
                except Exception:
                    benchmark_type = 'DEFAULT'
            
            # Merge everything into one record (simple format, no scores)
            merged_record = {
                # Static CSV fields
                'PREF_IBKR': symbol,
                'CMON': static_data.get('CMON') or static_data.get('cmon'),  # Try both cases
                'CGRUP': static_data.get('CGRUP') or static_data.get('cgrup'),  # Try both cases
                'GROUP': static_data.get('GROUP'),  # PRIMARY GROUP (file_group)
                'FINAL_THG': static_data.get('FINAL_THG'),
                'SHORT_FINAL': static_data.get('SHORT_FINAL'),
                'AVG_ADV': static_data.get('AVG_ADV'),
                'MAXALW': maxalw,  # Calculated: AVG_ADV / 10
                'SMI': static_data.get('SMI'),
                'SMA63chg': static_data.get('SMA63 chg'),  # Note: lowercase 'chg'
                'SMA246chg': static_data.get('SMA246 chg'),  # Note: lowercase 'chg'
                
                # Live market data (from Hammer) - lowercase keys
                'prev_close': market_data.get('prev_close'),
                'bid': market_data.get('bid'),
                'ask': market_data.get('ask'),
                'last': market_data.get('last') or market_data.get('price'),
                'volume': market_data.get('volume'),
                'spread_percent': spread_percent,
                
                # Symbol state
                'state': state,
                'state_reason': state_reason,
                'transition_reason': transition_reason if transition_reason else None,
                
                # Intent
                'intent': intent,
                'intent_reason': intent_reason,
                
                # Order plan
                'order_plan': order_plan,
                
                # Queue status
                'queue_status': queue_status,
                
                # Gate status
                'gate_status': gate_status,
                
                # User action
                'user_action': user_action_data.get('user_action'),
                'user_note': user_action_data.get('user_note'),
                'user_action_timestamp': user_action_data.get('timestamp'),
                
                # Execution status
                'execution_status': execution_result.get('execution_status'),
                'execution_reason': execution_result.get('execution_reason'),
                'execution_mode': execution_result.get('execution_mode'),
                
                # Signal interpretation
                'signal': signal_data.get('signal', {}),
                'signal_reason': signal_data.get('signal_reason', {}),
                
                # Rank data
                'fbtot_rank_raw': rank_data.get('fbtot_rank_raw'),
                'fbtot_rank_norm': rank_data.get('fbtot_rank_norm'),
                'sfstot_rank_raw': rank_data.get('sfstot_rank_raw'),
                'sfstot_rank_norm': rank_data.get('sfstot_rank_norm'),
                
                # Janall metrics (v1)
                'group_key': janall_metrics.get('group_key'),
                'benchmark_symbol': janall_metrics.get('benchmark_symbol'),
                'benchmark_chg': janall_metrics.get('benchmark_chg'),
                'benchmark_chg_percent': janall_metrics.get('benchmark_chg_percent'),
                'spread': janall_metrics.get('spread'),
                'mid': janall_metrics.get('mid'),
                'pf_bid_buy': janall_metrics.get('pf_bid_buy'),
                'pf_ask_sell': janall_metrics.get('pf_ask_sell'),
                'pf_front_buy': janall_metrics.get('pf_front_buy'),
                'pf_front_sell': janall_metrics.get('pf_front_sell'),
                'pf_bid_sell': janall_metrics.get('pf_bid_sell'),
                'pf_ask_buy': janall_metrics.get('pf_ask_buy'),
                'bid_buy_ucuzluk': janall_metrics.get('bid_buy_ucuzluk'),
                'ask_sell_pahalilik': janall_metrics.get('ask_sell_pahalilik'),
                'front_buy_ucuzluk': janall_metrics.get('front_buy_ucuzluk'),
                'front_sell_pahalilik': janall_metrics.get('front_sell_pahalilik'),
                'bid_sell_pahalilik': janall_metrics.get('bid_sell_pahalilik'),
                'ask_buy_ucuzluk': janall_metrics.get('ask_buy_ucuzluk'),
                'final_bb': janall_metrics.get('final_bb'),
                'final_fb': janall_metrics.get('final_fb'),
                'final_as': janall_metrics.get('final_as'),
                'final_fs': janall_metrics.get('final_fs'),
                'final_sas': janall_metrics.get('final_sas'),
                'final_sfs': janall_metrics.get('final_sfs'),
                'GORT': janall_metrics.get('gort'),  # For frontend consistency
                'gort': janall_metrics.get('gort'),
                'Fbtot': janall_metrics.get('fbtot'),  # For frontend consistency
                'fbtot': janall_metrics.get('fbtot'),
                'SFStot': janall_metrics.get('sfstot'),  # For frontend consistency
                'sfstot': janall_metrics.get('sfstot'),
                'janall_breakdown': janall_metrics.get('_breakdown'),  # For Inspector
                
                # GRPAN metrics
                'grpan_price': grpan_metrics.get('grpan_price'),
                'grpan_concentration_percent': grpan_metrics.get('concentration_percent'),
                'grpan_real_lot_count': grpan_metrics.get('real_lot_count'),
                'grpan_print_count': grpan_metrics.get('print_count'),
                'grpan_weighted_price_frequency': grpan_metrics.get('weighted_price_frequency', {}),
                'grpan_breakdown': grpan_metrics.get('breakdown', {}),  # For Inspector
                
                # GRPAN windows (PAN values)
                'pan_10m': grpan_all_windows.get('pan_10m', {}),
                'pan_30m': grpan_all_windows.get('pan_30m', {}),
                'pan_1h': grpan_all_windows.get('pan_1h', {}),
                'pan_3h': grpan_all_windows.get('pan_3h', {}),
                'pan_1d': grpan_all_windows.get('pan_1d', {}),
                'pan_3d': grpan_all_windows.get('pan_3d', {}),
                
                # GOD (GRPAN ORT DEV) = last_price - average of all GRPAN windows
                'grpan_ort_dev': None,  # Will be calculated below
                
                # RWVAP windows and ROD
                'rwvap_windows': rwvap_windows_data,
                'rwvap_ort_dev': None,  # Will be calculated below
                
                # Position analytics
                'position_analytics': position_analytics,
                
                # Exposure mode
                'exposure_mode': exposure_mode,
                
                # PSFALGO position snapshot
                'befday_qty': psfalgo_snapshot.get('befday_qty'),
                'current_qty': psfalgo_snapshot.get('current_qty'),
                'potential_qty': psfalgo_snapshot.get('potential_qty'),
                'open_buy_qty': psfalgo_snapshot.get('open_buy_qty'),
                'open_sell_qty': psfalgo_snapshot.get('open_sell_qty'),
                'befday_cost_raw': psfalgo_snapshot.get('befday_cost_raw'),
                'befday_cost_adj': psfalgo_snapshot.get('befday_cost_adj'),
                'used_befday_cost': psfalgo_snapshot.get('used_befday_cost'),
                'position_state': psfalgo_snapshot.get('position_state'),
                'todays_avg_cost_long': psfalgo_snapshot.get('todays_avg_cost_long'),
                'todays_avg_cost_short': psfalgo_snapshot.get('todays_avg_cost_short'),
                
                # PSFALGO guards
                'maxalw': psfalgo_guards.get('maxalw'),
                'maxalw_exceeded_current': psfalgo_guards.get('maxalw_exceeded_current'),
                'maxalw_exceeded_potential': psfalgo_guards.get('maxalw_exceeded_potential'),
                'daily_add_used': psfalgo_guards.get('daily_add_used'),
                'daily_add_limit': psfalgo_guards.get('daily_add_limit'),
                'daily_add_remaining': psfalgo_guards.get('daily_add_remaining'),
                'change_3h_net': psfalgo_guards.get('change_3h_net'),
                'change_3h_limit': psfalgo_guards.get('change_3h_limit'),
                'change_3h_remaining': psfalgo_guards.get('change_3h_remaining'),
                'cross_blocked': psfalgo_guards.get('cross_blocked'),
                'cross_block_reason': psfalgo_guards.get('cross_block_reason'),
                'guard_status': psfalgo_guards.get('guard_status'),
                'guard_reason': psfalgo_guards.get('guard_reason'),
                'allowed_actions': psfalgo_guards.get('allowed_actions'),
                
                # PSFALGO action plan
                'psfalgo_action_plan': psfalgo_action_plan,
            }
            
            # Calculate GOD (GRPAN ORT DEV) = last_price - average of all GRPAN windows
            last_price = market_data.get('last') or market_data.get('price')
            if last_price and grpan_all_windows:
                window_names = ['pan_10m', 'pan_30m', 'pan_1h', 'pan_3h', 'pan_1d', 'pan_3d']
                valid_prices = []
                for window_name in window_names:
                    window_data = grpan_all_windows.get(window_name, {})
                    grpan_price = window_data.get('grpan_price')
                    if grpan_price is not None and isinstance(grpan_price, (int, float)) and not (grpan_price != grpan_price or grpan_price == float('inf') or grpan_price == float('-inf')):
                        valid_prices.append(float(grpan_price))
                
                if valid_prices:
                    grpan_ort = sum(valid_prices) / len(valid_prices)
                    merged_record['grpan_ort_dev'] = float(last_price) - grpan_ort
            
            # Calculate ROD (RWVAP ORT DEV) = last_price - average of all RWVAP windows
            if last_price and rwvap_windows_data:
                rwvap_window_names = ['rwvap_1d', 'rwvap_3d', 'rwvap_5d']
                valid_rwvap_prices = []
                for window_name in rwvap_window_names:
                    window_data = rwvap_windows_data.get(window_name, {})
                    rwvap_price = window_data.get('rwvap') or window_data.get('rwvap_price')
                    if rwvap_price is not None and isinstance(rwvap_price, (int, float)) and not (rwvap_price != rwvap_price or rwvap_price == float('inf') or rwvap_price == float('-inf')):
                        valid_rwvap_prices.append(float(rwvap_price))
                
                if valid_rwvap_prices:
                    rwvap_ort = sum(valid_rwvap_prices) / len(valid_rwvap_prices)
                    merged_record['rwvap_ort_dev'] = float(last_price) - rwvap_ort
            
            # Get pricing overlay scores (from cache, may be COLLECTING if not computed yet)
            overlay_scores = {}
            if pricing_overlay_engine:
                overlay_scores = pricing_overlay_engine.get_overlay_scores(symbol) or {}
            
            # If overlay_scores is empty (not computed yet), set status to COLLECTING
            if not overlay_scores:
                overlay_scores = {'status': 'COLLECTING'}
            
            # Add overlay scores to merged_record
            # Use CGRUP-based benchmark_type if overlay doesn't have it
            overlay_benchmark_type = overlay_scores.get('benchmark_type') or benchmark_type
            merged_record.update({
                'overlay_status': overlay_scores.get('status', 'COLLECTING'),
                'overlay_benchmark_type': overlay_benchmark_type,  # CGRUP-based (Janall logic)
                'overlay_benchmark_chg': overlay_scores.get('benchmark_chg'),
                'Bid_buy_ucuzluk_skoru': overlay_scores.get('Bid_buy_ucuzluk_skoru'),
                'Front_buy_ucuzluk_skoru': overlay_scores.get('Front_buy_ucuzluk_skoru'),
                'Ask_buy_ucuzluk_skoru': overlay_scores.get('Ask_buy_ucuzluk_skoru'),
                'Ask_sell_pahalilik_skoru': overlay_scores.get('Ask_sell_pahalilik_skoru'),
                'Front_sell_pahalilik_skoru': overlay_scores.get('Front_sell_pahalilik_skoru'),
                'Bid_sell_pahalilik_skoru': overlay_scores.get('Bid_sell_pahalilik_skoru'),
                'Final_BB_skor': overlay_scores.get('Final_BB_skor'),
                'Final_FB_skor': overlay_scores.get('Final_FB_skor'),
                'Final_AB_skor': overlay_scores.get('Final_AB_skor'),
                'Final_AS_skor': overlay_scores.get('Final_AS_skor'),
                'Final_FS_skor': overlay_scores.get('Final_FS_skor'),
                'Final_BS_skor': overlay_scores.get('Final_BS_skor'),
                'Final_SAS_skor': overlay_scores.get('Final_SAS_skor'),
                'Final_SFS_skor': overlay_scores.get('Final_SFS_skor'),
                'Final_SBS_skor': overlay_scores.get('Final_SBS_skor'),
                'overlay_spread': overlay_scores.get('Spread'),
            })
            
            merged_data.append(merged_record)
        
        logger.info(f"Returning {len(merged_data)} merged records")
        
        return {
            "success": True,
            "data": merged_data,
            "count": len(merged_data)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting merged market data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/merged/{symbol}")
async def get_merged_market_data_symbol(symbol: str):
    """
    Get merged data for a single symbol
    
    Args:
        symbol: PREF_IBKR symbol
        
    Returns:
        Merged record with static fields, live fields, and derived scores
    """
    try:
        # Services are initialized at startup - no need to reinitialize here
        if not static_store or not static_store.is_loaded():
            raise HTTPException(
                status_code=404,
                detail="Static data not loaded. Please load janalldata.csv first."
            )
        
        # Get static data
        static_data = static_store.get_static_data(symbol)
        if not static_data:
            raise HTTPException(
                status_code=404,
                detail=f"Static data not found for {symbol}"
            )
        
        # Get live market data (must include prev_close from Hammer)
        market_data = market_data_cache.get(symbol, {})
        if not market_data:
            market_data = {
                'bid': None,
                'ask': None,
                'last': None,
                'price': None,
                'spread': None,
                'volume': None,
                'prev_close': None
            }
        
        # CRITICAL: prev_close MUST come from Hammer getSymbolSnapshot, NOT from CSV
        # CSV fallback removed - Hammer is the single source of truth (dividend/split adjusted)
        # NOTE: We do NOT fetch snapshot here in get_symbol_data - too many API calls
        # Snapshot is fetched lazily in update_market_data_cache() when L1Update arrives
        # If prev_close is missing here, it means snapshot hasn't been fetched yet (normal)
        # UI will show N/A until L1Update triggers snapshot fetch
        
        # Calculate spread if not provided
        if market_data.get('spread') is None:
            bid = market_data.get('bid')
            ask = market_data.get('ask')
            if bid and ask and bid > 0 and ask > 0:
                market_data['spread'] = ask - bid
            else:
                market_data['spread'] = 0.0
        
        # Compute derived scores
        derived_result = metrics_engine.compute_scores(
            symbol=symbol,
            market_data=market_data,
            static_data=static_data
        )
        
        # Calculate spread_percent
        spread_percent = None
        bid = market_data.get('bid')
        ask = market_data.get('ask')
        if bid and ask and bid > 0 and ask > 0:
            spread = ask - bid
            mid_price = (bid + ask) / 2
            if mid_price > 0:
                spread_percent = (spread / mid_price) * 100
        
        # Compute symbol state
        state = 'IDLE'  # Default
        if state_engine:
            state = state_engine.compute_state(symbol, static_data, market_data)
        
        # Merge everything
        merged_record = {
            'PREF_IBKR': symbol,
            'CMON': static_data.get('CMON'),
            'CGRUP': static_data.get('CGRUP'),
            'FINAL_THG': static_data.get('FINAL_THG'),
            'SHORT_FINAL': static_data.get('SHORT_FINAL'),
            'AVG_ADV': static_data.get('AVG_ADV'),
            'SMI': static_data.get('SMI'),
            'SMA63chg': static_data.get('SMA63 chg'),
            'SMA246chg': static_data.get('SMA246 chg'),
            'bid': market_data.get('bid'),
            'ask': market_data.get('ask'),
            'last': market_data.get('last') or market_data.get('price'),
            'volume': market_data.get('volume'),
            'spread_percent': spread_percent,
            'state': state,
        }
        
        return {
            "success": True,
            "data": merged_record
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting merged market data for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snapshot/preferred")
async def get_preferred_snapshot():
    """
    Get initial snapshot of preferred stocks market data (bid/ask/last).
    This is called by frontend AFTER subscribing, when cache should be filled.
    
    Returns:
        Dict with symbol -> {bid, ask, last, prev_close, spread, volume}
        Returns empty if cache not yet filled (non-critical - WebSocket will provide updates)
    """
    try:
        global market_data_cache
        
        # Early return if cache is empty (Hammer hasn't pushed data yet)
        if not market_data_cache or len(market_data_cache) == 0:
            logger.debug("📸 Snapshot: Cache empty, returning 0 (WebSocket will provide updates when data arrives)")
            return {
                "success": True,
                "data": [],
                "count": 0,
                "message": "Cache not yet filled, WebSocket will provide updates"
            }
        
        snapshot = {}
        for symbol, market_data in market_data_cache.items():
            # Only include preferred stocks (exclude ETFs)
            if symbol not in ETF_TICKERS:
                # Only include if we have at least bid OR ask OR last (meaningful data)
                if market_data.get('bid') is not None or market_data.get('ask') is not None or market_data.get('last') is not None:
                    snapshot[symbol] = {
                        'PREF_IBKR': symbol,
                        'bid': market_data.get('bid'),
                        'ask': market_data.get('ask'),
                        'last': market_data.get('last') or market_data.get('price'),
                        'prev_close': market_data.get('prev_close'),
                        'spread': market_data.get('spread'),
                        'volume': market_data.get('volume')
                    }
        
        logger.info(f"📸 Snapshot: Returning {len(snapshot)} preferred stocks with market data")
        return {
            "success": True,
            "data": list(snapshot.values()),
            "count": len(snapshot)
        }
    except Exception as e:
        logger.error(f"Error getting preferred snapshot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snapshot/etf")
async def get_etf_snapshot():
    """
    Get initial snapshot of ETF market data.
    This is called by frontend AFTER subscribing, when cache should be filled.
    
    Returns:
        List of ETF data with last, prev_close, daily_change_percent, etc.
        Returns empty if cache not yet filled (non-critical - WebSocket will provide updates)
    """
    try:
        etf_data = get_etf_market_data()
        
        # Early return if ETF data is empty (Hammer hasn't pushed data yet)
        if not etf_data or len(etf_data) == 0:
            logger.debug("📸 ETF Snapshot: Cache empty, returning 0 (WebSocket will provide updates when data arrives)")
            return {
                "success": True,
                "data": [],
                "count": 0,
                "message": "Cache not yet filled, WebSocket will provide updates"
            }
        
        snapshot = []
        for symbol, data in etf_data.items():
            # Only include if we have meaningful data (at least last or prev_close)
            if data.get('last') is not None or data.get('prev_close') is not None:
                snapshot.append({
                    'symbol': symbol,
                    'last': data.get('last'),
                    'prev_close': data.get('prev_close'),
                    'daily_change_percent': data.get('daily_change_percent'),
                    'daily_change_cents': data.get('daily_change_cents'),
                    'bid': data.get('bid'),
                    'ask': data.get('ask')
                })
        
        logger.info(f"📸 ETF Snapshot: Returning {len(snapshot)} ETFs with market data")
        return {
            "success": True,
            "data": snapshot,
            "count": len(snapshot)
        }
    except Exception as e:
        logger.error(f"Error getting ETF snapshot: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/load-csv")
async def load_csv():
    """
    Reload CSV endpoint - Reloads both DataFabric and StaticDataStore from CSV files.
    
    This endpoint is called by the frontend "Reload CSV" button.
    It reloads:
    - DataFabric static data (from janalldata.csv)
    - StaticDataStore (from janall/janalldata.csv)
    
    ⚠️ Note: This will change algo's view of static data mid-session.
    """
    global static_store
    
    try:
        logger.info("📊 CSV reload requested via /load-csv endpoint")
        
        # Ensure static_store is initialized
        if static_store is None:
            logger.info("📊 StaticStore not initialized, initializing now...")
            static_store = StaticDataStore()
            # Sync with global instance in static_data_store module
            from app.market_data.static_data_store import initialize_static_store
            initialize_static_store()
        
        # 1. Reload DataFabric static data
        from app.core.data_fabric import get_data_fabric
        fabric = get_data_fabric()
        fabric_success = fabric.reload_static()
        
        # 2. Reload StaticDataStore
        store_success = False
        store_error = None
        try:
            store_success = static_store.load_csv()
            if not store_success:
                # Try to get more info about why it failed
                from pathlib import Path
                csv_path = getattr(static_store, 'csv_path', None)
                if csv_path:
                    csv_path_obj = Path(csv_path)
                else:
                    # Try to find CSV file manually
                    possible_paths = [
                        Path(r"C:\Users\User\OneDrive\Masaüstü\Proje\StockTracker\janall") / 'janalldata.csv',
                        Path(os.getcwd()) / 'janall' / 'janalldata.csv',
                        Path(os.getcwd()) / 'janalldata.csv',
                    ]
                    csv_path_obj = None
                    for path in possible_paths:
                        if path.exists():
                            csv_path_obj = path
                            break
                
                if csv_path_obj and not csv_path_obj.exists():
                    store_error = f"CSV file not found: {csv_path_obj}"
                else:
                    store_error = "CSV load returned False (check server logs for details)"
        except Exception as e:
            store_error = str(e)
            logger.error(f"Exception during StaticStore.load_csv(): {e}", exc_info=True)
        
        if fabric_success and store_success:
            symbol_count = len(static_store.get_all_symbols()) if static_store else 0
            logger.info(f"✅ CSV reloaded successfully: {symbol_count} symbols")
            
            return {
                "success": True,
                "message": f"CSV reloaded successfully: {symbol_count} symbols",
                "count": symbol_count,
                "datafabric_reloaded": fabric_success,
                "staticstore_reloaded": store_success
            }
        else:
            error_msg = f"Partial reload: DataFabric={fabric_success}, StaticStore={store_success}"
            if store_error:
                error_msg += f" (Error: {store_error})"
            logger.warning(f"⚠️ {error_msg}")
            raise HTTPException(
                status_code=500,
                detail=error_msg
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reloading CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload-csv")
async def reload_csv_admin():
    """
    ADMIN ONLY: Manual CSV reload endpoint (default: disabled)
    
    This endpoint actually reloads static_store from CSV.
    Use with caution - it will change algo's view of the world mid-session.
    
    To enable: Set ENABLE_CSV_RELOAD=true in environment or config.
    """
    from app.config.settings import settings
    
    # Check if manual reload is enabled
    if not getattr(settings, 'ENABLE_CSV_RELOAD', False):
        raise HTTPException(
            status_code=403,
            detail="Manual CSV reload is disabled. Set ENABLE_CSV_RELOAD=true to enable. "
                   "Note: This will change algo's static data mid-session."
        )
    
    try:
        # Services already initialized at startup
        # This is an admin endpoint - CSV reload is intentional
        logger.warning("⚠️ ADMIN: Manual CSV reload requested - this will change static_store mid-session!")
        
        success = static_store.load_csv()
        if success:
            symbol_count = len(static_store.get_all_symbols())
            
            # Subscribe to all symbols for GRPAN (L2 subscription needed for trade prints)
            hammer_feed = get_hammer_feed()
            symbols = static_store.get_all_symbols()
            
            # NOTE: GRPANTickFetcher is now handled by worker process
            # We do NOT add symbols here to avoid duplicate bootstrap
            # Worker will handle all GRPAN bootstrap when processing jobs
            logger.info("📊 GRPAN tick fetching handled by worker (not in backend)")
            
            if hammer_feed:
                logger.info(f"🔄 Subscribing to {len(symbols)} symbols for GRPAN (L2)...")
                
                # Subscribe in background to avoid blocking API response
                import threading
                def subscribe_background():
                    try:
                        subscribed = hammer_feed.subscribe_symbols_batch(
                            symbols, 
                            include_l2=True,  # L2 needed for trade prints
                            batch_size=50
                        )
                        logger.info(f"✅ GRPAN subscription complete: {subscribed}/{len(symbols)} symbols")
                    except Exception as e:
                        logger.error(f"Error in background subscription: {e}", exc_info=True)
                
                thread = threading.Thread(target=subscribe_background, daemon=True)
                thread.start()
                logger.info(f"🚀 Background L2 subscription started for {len(symbols)} symbols")
            else:
                logger.warning("Hammer feed not available - skipping GRPAN subscription")
            
            logger.warning(f"⚠️ ADMIN: CSV reloaded - {symbol_count} symbols (algo's static data changed mid-session!)")
            
            return {
                "success": True,
                "message": f"ADMIN: Reloaded {symbol_count} symbols. L2 subscription started in background for GRPAN.",
                "count": symbol_count,
                "warning": "static_store was changed mid-session - algo's view of the world has changed!"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to reload CSV file"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reloading CSV: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# 🟢 FAST PATH ENDPOINTS - For instant UI display
# =============================================================================

@router.get("/fast/all")
async def get_fast_path_data():
    """
    🟢 FAST PATH - Get instant L1 + FAST scores for all symbols.
    
    This endpoint is optimized for:
    - Instant UI display (no waiting for tick-by-tick)
    - Trading algo data (RUNALL, ADDNEWPOS, KARBOTU)
    
    Returns:
        - L1 data: bid, ask, last, volume
        - Static data: prev_close, FINAL_THG, AVG_ADV
        - FAST scores: Final_BB, Final_FB, Fbtot, SFStot, GORT
    
    ⚠️ Does NOT include: GOD, ROD, GRPAN (use /deep-analysis for those)
    """
    try:
        from app.core.data_fabric import get_data_fabric
        from app.core.fast_score_calculator import get_fast_score_calculator
        
        fabric = get_data_fabric()
        
        # Check if DataFabric static data is loaded (FAST PATH only needs static data)
        # Live data is optional - we can return static data even without live updates
        status = fabric.get_status()
        if status.get('static_status') != 'READY':
            logger.warning("⚠️ DataFabric static data not ready - returning empty data")
            return {
                "success": True,
                "path": "FAST",
                "count": 0,
                "data": [],
                "status": status,
                "message": "DataFabric static data not loaded. Please wait for startup to complete."
            }
        
        calculator = get_fast_score_calculator()
        
        # Get all FAST snapshots from DataFabric
        fast_data_dict = fabric.get_all_fast_snapshots()
        
        # Convert object {symbol: data} to array for frontend compatibility
        # Also clean NaN values (JSON doesn't support NaN)
        import math
        
        def clean_nan_values(obj):
            """Recursively replace NaN with None for JSON serialization"""
            if isinstance(obj, dict):
                return {k: clean_nan_values(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [clean_nan_values(item) for item in obj]
            elif isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
                return None
            else:
                return obj
        
        fast_data_array = [
            clean_nan_values({**data, 'PREF_IBKR': symbol})  # Add PREF_IBKR field and clean NaN
            for symbol, data in fast_data_dict.items()
        ]
        
        # Get status
        status = fabric.get_status()
        
        return {
            "success": True,
            "path": "FAST",
            "count": len(fast_data_array),
            "data": fast_data_array,  # Array format for frontend compatibility
            "status": {
                "static_symbols": status.get('static_symbols', 0),
                "live_symbols": status.get('live_symbols', 0),
                "derived_symbols": status.get('derived_symbols', 0),
            }
        }
    except Exception as e:
        logger.error(f"Error in fast path data: {e}", exc_info=True)
        # Return JSON error response (not HTML)
        return {
            "success": False,
            "path": "FAST",
            "error": str(e),
            "count": 0,
            "data": [],
            "status": {
                "static_symbols": 0,
                "live_symbols": 0,
                "derived_symbols": 0,
            }
        }


@router.get("/fast/{symbol}")
async def get_fast_path_symbol(symbol: str):
    """
    🟢 FAST PATH - Get instant L1 + FAST scores for a single symbol.
    """
    try:
        from app.core.data_fabric import get_data_fabric
        
        fabric = get_data_fabric()
        fast_snapshot = fabric.get_fast_snapshot(symbol)
        
        if not fast_snapshot:
            raise HTTPException(
                status_code=404,
                detail=f"No data for symbol: {symbol}"
            )
        
        return {
            "success": True,
            "path": "FAST",
            "symbol": symbol,
            "data": fast_snapshot
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in fast path symbol: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fast/compute")
async def compute_fast_scores():
    """
    🟢 FAST PATH - Trigger batch computation of FAST scores.
    
    This will:
    1. Compute all L1-based scores (bid_buy_ucuzluk, Final_BB, etc.)
    2. Compute group-based scores (Fbtot, SFStot, GORT)
    3. Update DataFabric with results
    
    Use this after market data is loaded to pre-compute scores.
    """
    try:
        from app.core.fast_score_calculator import get_fast_score_calculator
        
        calculator = get_fast_score_calculator()
        results = calculator.compute_all_fast_scores(include_group_metrics=True)
        
        return {
            "success": True,
            "path": "FAST",
            "computed_symbols": len(results),
            "stats": calculator.get_stats()
        }
    except Exception as e:
        logger.error(f"Error computing fast scores: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# 🔵 SLOW PATH ENDPOINTS - For Deeper Analysis (tick-by-tick)
# =============================================================================

@router.get("/deep-analysis/all")
async def get_deep_analysis_all():
    """
    🔵 SLOW PATH - Get tick-by-tick analysis (GOD, ROD, GRPAN, RWVAP) for all symbols.
    
    ⚠️ This data is:
    - Lazy loaded (only available after tick-by-tick is enabled)
    - NOT required for trading algo (RUNALL, ADDNEWPOS, KARBOTU)
    - For advanced analysis only
    
    Returns:
        - GRPAN: grpan_price, grpan_concentration_percent, grpan_ort_dev (GOD)
        - RWVAP: rwvap_1d, rwvap_ort_dev (ROD)
        - Static data: prev_close, bid, ask, last, volume, AVG_ADV, CGRUP
    """
    try:
        from app.core.data_fabric import get_data_fabric
        
        fabric = get_data_fabric()
        
        # Check if tick-by-tick is enabled
        if not fabric.is_tick_by_tick_enabled():
            return {
                "success": True,
                "path": "SLOW",
                "enabled": False,
                "message": "Tick-by-tick analysis is not enabled. Enable it first via /deep-analysis/enable",
                "data": {}
            }
        
        # Get all symbols from static store
        if not static_store or not static_store.is_loaded():
            return {
                "success": True,
                "path": "SLOW",
                "enabled": True,
                "count": 0,
                "data": {},
                "message": "Static data not loaded"
            }
        
        symbols = static_store.get_all_symbols()
        if not symbols:
            return {
                "success": True,
                "path": "SLOW",
                "enabled": True,
                "count": 0,
                "data": {}
            }
        
        # Get engines
        grpan_engine = get_grpan_engine()
        rwvap_engine = get_rwvap_engine()
        
        # Build deep analysis data for all symbols
        deep_data = {}
        
        symbols_with_grpan = 0
        symbols_with_rwvap = 0
        
        # Use global market_data_cache (defined at module level)
        global market_data_cache
        
        for symbol in symbols:
            # Get static data
            static_data = static_store.get_static_data(symbol)
            if not static_data:
                continue
            
            # Get live market data
            market_data = market_data_cache.get(symbol, {})
            if not market_data:
                # Still include symbol even without live data
                market_data = {
                    'bid': None,
                    'ask': None,
                    'last': None,
                    'volume': None
                }
            
            # Get GRPAN data
            grpan_price = None
            grpan_concentration_percent = None
            grpan_ort_dev = None  # GOD
            
            if grpan_engine:
                # Get latest_pan (backward compatible)
                grpan_metrics = grpan_engine.get_grpan_for_symbol(symbol)
                grpan_price = grpan_metrics.get('grpan_price')
                grpan_concentration_percent = grpan_metrics.get('concentration_percent')
                
                if grpan_price is not None:
                    symbols_with_grpan += 1
                
                # Get all windows for GOD calculation
                grpan_all_windows = grpan_engine.get_all_windows_for_symbol(symbol)
                if grpan_all_windows:
                    last_price = market_data.get('last') or market_data.get('price')
                    if last_price:
                        window_names = ['pan_10m', 'pan_30m', 'pan_1h', 'pan_3h', 'pan_1d', 'pan_3d']
                        valid_prices = []
                        for window_name in window_names:
                            window_data = grpan_all_windows.get(window_name, {})
                            window_grpan_price = window_data.get('grpan_price')
                            if window_grpan_price is not None and isinstance(window_grpan_price, (int, float)):
                                if not (window_grpan_price != window_grpan_price or window_grpan_price == float('inf') or window_grpan_price == float('-inf')):
                                    valid_prices.append(float(window_grpan_price))
                        
                        if valid_prices:
                            grpan_ort = sum(valid_prices) / len(valid_prices)
                            grpan_ort_dev = float(last_price) - grpan_ort
            
            # Get RWVAP data
            rwvap_1d = None
            rwvap_ort_dev = None  # ROD
            rwvap_windows = {}
            
            if rwvap_engine:
                rwvap_windows = rwvap_engine.get_all_rwvap_for_symbol(symbol) or {}
                rwvap_1d_data = rwvap_windows.get('rwvap_1d', {})
                rwvap_1d = rwvap_1d_data.get('rwvap') or rwvap_1d_data.get('rwvap_price')
                
                if rwvap_1d is not None:
                    symbols_with_rwvap += 1
                
                # Calculate ROD (RWVAP ORT DEV)
                last_price = market_data.get('last') or market_data.get('price')
                if last_price and rwvap_windows:
                    rwvap_window_names = ['rwvap_1d', 'rwvap_3d', 'rwvap_5d']
                    valid_rwvap_prices = []
                    for window_name in rwvap_window_names:
                        window_data = rwvap_windows.get(window_name, {})
                        rwvap_price = window_data.get('rwvap') or window_data.get('rwvap_price')
                        if rwvap_price is not None and isinstance(rwvap_price, (int, float)):
                            if not (rwvap_price != rwvap_price or rwvap_price == float('inf') or rwvap_price == float('-inf')):
                                valid_rwvap_prices.append(float(rwvap_price))
                    
                    if valid_rwvap_prices:
                        rwvap_ort = sum(valid_rwvap_prices) / len(valid_rwvap_prices)
                        rwvap_ort_dev = float(last_price) - rwvap_ort
            
            # Get tick count from DataFabric if available
            tick_count = 0
            if fabric.is_tick_by_tick_enabled():
                symbol_deep = fabric.get_deep_analysis(symbol)
                if symbol_deep:
                    tick_count = symbol_deep.get('tick_count', 0)
            
            # Build record
            deep_data[symbol] = {
                'PREF_IBKR': symbol,
                'CGRUP': static_data.get('CGRUP') or static_data.get('cgroup'),
                'prev_close': static_data.get('prev_close'),
                'bid': market_data.get('bid'),
                'ask': market_data.get('ask'),
                'last': market_data.get('last') or market_data.get('price'),
                'spread': (market_data.get('ask') - market_data.get('bid')) if (market_data.get('ask') and market_data.get('bid')) else None,
                'volume': market_data.get('volume'),
                'AVG_ADV': static_data.get('AVG_ADV'),
                # GRPAN metrics
                'grpan_price': grpan_price,
                'grpan_concentration_percent': grpan_concentration_percent,
                'grpan_ort_dev': grpan_ort_dev,  # GOD
                # RWVAP metrics
                'rwvap_1d': rwvap_1d,
                'rwvap_ort_dev': rwvap_ort_dev,  # ROD
                # RWVAP windows (for frontend)
                'rwvap_windows': rwvap_windows if rwvap_engine else {},
                # Tick count
                'tick_count': tick_count
            }
        
        logger.info(
            f"🔵 SLOW PATH: Deep analysis data for {len(deep_data)} symbols "
            f"(GRPAN: {symbols_with_grpan}, RWVAP: {symbols_with_rwvap})"
        )
        
        return {
            "success": True,
            "path": "SLOW",
            "enabled": True,
            "count": len(deep_data),
            "data": deep_data,
            "stats": {
                "total_symbols": len(deep_data),
                "symbols_with_grpan": symbols_with_grpan,
                "symbols_with_rwvap": symbols_with_rwvap
            }
        }
    except Exception as e:
        logger.error(f"Error in deep analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deep-analysis/{symbol}")
async def get_deep_analysis_symbol(symbol: str):
    """
    🔵 SLOW PATH - Get tick-by-tick analysis for a single symbol.
    """
    try:
        from app.core.data_fabric import get_data_fabric
        
        fabric = get_data_fabric()
        
        if not fabric.is_tick_by_tick_enabled():
            return {
                "success": True,
                "path": "SLOW",
                "enabled": False,
                "symbol": symbol,
                "message": "Tick-by-tick analysis is not enabled",
                "data": None
            }
        
        deep_data = fabric.get_deep_analysis(symbol)
        
        return {
            "success": True,
            "path": "SLOW",
            "enabled": True,
            "symbol": symbol,
            "data": deep_data
        }
    except Exception as e:
        logger.error(f"Error in deep analysis symbol: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/execution/mode")
async def get_execution_mode():
    """
    Get current execution mode (PREVIEW, SEMI_AUTO, FULL_AUTO).
    """
    try:
        global execution_router
        if execution_router is None:
            # Initialize if not already done
            initialize_market_data_services()
        
        if execution_router:
            current_mode = execution_router.get_mode()
            mode_value = current_mode.value if hasattr(current_mode, 'value') else str(current_mode)
            return {
                "success": True,
                "mode": mode_value
            }
        else:
            return {
                "success": True,
                "mode": "PREVIEW"
            }
    except Exception as e:
        logger.error(f"Error getting execution mode: {e}", exc_info=True)
        return {
            "success": True,
            "mode": "PREVIEW"  # Default fallback
        }


@router.post("/execution/mode")
async def set_execution_mode(request: Dict[str, Any] = Body(...)):
    """
    Set execution mode (PREVIEW, SEMI_AUTO, FULL_AUTO).
    
    Accepts mode as JSON body: {"mode": "PREVIEW"}
    """
    try:
        # Get mode from request body
        mode_str = request.get('mode')
        if not mode_str:
            raise HTTPException(status_code=400, detail="Mode parameter required in request body")
        
        global execution_router
        
        # Validate mode
        valid_modes = ['PREVIEW', 'SEMI_AUTO', 'FULL_AUTO']
        if mode_str not in valid_modes:
            raise HTTPException(status_code=400, detail=f"Invalid mode: {mode_str}. Must be one of {valid_modes}")
        
        # Initialize if not already done
        if execution_router is None:
            initialize_market_data_services()
        
        if execution_router:
            execution_mode = ExecutionMode[mode_str]
            execution_router.set_mode(execution_mode)
            logger.info(f"Execution mode set to: {mode_str}")
        
        return {
            "success": True,
            "mode": mode_str
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting execution mode: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deep-analysis/enable")
async def enable_deep_analysis(enabled: bool = True):
    """
    🔵 SLOW PATH - Enable/disable tick-by-tick data collection.
    
    ⚠️ Only enable when you need GOD/ROD/GRPAN data.
    Disabling saves CPU and memory.
    
    When enabled:
    - Starts GRPANTickFetcher (bootstrap/recovery mode)
    - Enables trade print routing from Hammer L1Updates
    - Bootstraps all symbols (rate-limited, not all at once)
    """
    try:
        from app.core.data_fabric import get_data_fabric
        
        fabric = get_data_fabric()
        fabric.enable_tick_by_tick(enabled)
        
        # NOTE: GRPAN bootstrap is now handled by worker process (deeper_analysis_worker.py)
        # We do NOT start GRPANTickFetcher here to avoid blocking backend terminal
        # Worker will handle all GRPAN bootstrap when processing jobs from Redis queue
        # This endpoint only sets the flag for backward compatibility
        
        if enabled:
            logger.info("🔵 SLOW PATH: Tick-by-tick flag enabled (GRPAN bootstrap will be handled by worker)")
        else:
            logger.info("⚫ SLOW PATH: Tick-by-tick flag disabled")
        
        return {
            "success": True,
            "path": "SLOW",
            "tick_by_tick_enabled": enabled,
            "message": f"Tick-by-tick analysis {'enabled' if enabled else 'disabled'} (bootstrap handled by worker)"
        }
    except Exception as e:
        logger.error(f"Error enabling deep analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

