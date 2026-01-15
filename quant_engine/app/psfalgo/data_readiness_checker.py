"""
Data Readiness Checker - Phase 8 (FAST PATH OPTIMIZED)

Checks if MarketSnapshot/Scanner Layer is ready for RUNALL.
Provides data readiness metrics and health checks.

🎯 CRITICAL: TWO-PATH ARCHITECTURE
==================================

🟢 FAST PATH (Required for RUNALL):
- L1 data: bid, ask, last
- Static data: prev_close, FINAL_THG
- FAST scores: Fbtot, Final_BB (calculated from L1 + CSV)

🔵 SLOW PATH (NOT required for RUNALL):
- GOD, ROD, GRPAN
- These are for Deeper Analysis ONLY
- Algo NEVER waits for these

⚠️ GATING CONDITIONS:
- ONLY L1 data + prev_close + Fbtot are gating
- GOD/ROD/GRPAN are NEVER gating conditions
- Algo can start as soon as L1 + CSV data is ready

Key Principles:
- SADECE kontrol eder
- Karar vermez
- Execution yapmaz
- Decision logic'e dokunmaz
- GOD/ROD/GRPAN ASLA gating condition OLMAZ
"""

from typing import Dict, Any, List, Optional
from collections import Counter

from app.core.logger import logger
from app.psfalgo.market_snapshot_store import get_market_snapshot_store
from app.market_data.static_data_store import StaticDataStore
from app.api.websocket_routes import get_static_store
from app.core.data_fabric import get_data_fabric


class DataReadinessChecker:
    """
    Data Readiness Checker - checks if data is ready for RUNALL.
    
    🎯 TWO-PATH ARCHITECTURE:
    
    🟢 FAST PATH (Gating for RUNALL):
    - L1 data: bid, ask, last ✓
    - prev_close ✓
    - Fbtot ✓
    
    🔵 SLOW PATH (NOT Gating - Optional):
    - GOD ❌ (never gating)
    - ROD ❌ (never gating)  
    - GRPAN ❌ (never gating)
    
    Responsibilities:
    - Check MarketSnapshot readiness (FAST PATH only)
    - Count symbols with required fields
    - Identify missing fields
    - Provide sample symbols
    
    Does NOT:
    - Make trading decisions
    - Execute orders
    - Modify data
    - Wait for GOD/ROD/GRPAN (tick-by-tick)
    """
    
    def __init__(self):
        """Initialize Data Readiness Checker"""
        logger.info("DataReadinessChecker initialized")
    
    def check_data_readiness(self) -> Dict[str, Any]:
        """
        Check data readiness for RUNALL.
        
        Returns:
            Data readiness report
        """
        snapshot_store = get_market_snapshot_store()
        static_store = get_static_store()
        
        # Get all current snapshots from MarketSnapshotStore
        all_snapshots = {}
        if snapshot_store:
            all_snapshots = snapshot_store.get_all_current_snapshots()
        
        # ALSO check market_data_cache (fallback for live prices)
        market_data_cache = {}
        try:
            from app.api.market_data_routes import market_data_cache as mdc
            market_data_cache = mdc or {}
        except Exception:
            pass
        
        # Get all symbols from static store
        all_symbols = []
        if static_store:
            all_symbols = static_store.get_all_symbols()
        
        # Count symbols with required fields
        symbols_with_live_prices = 0
        symbols_with_prev_close = 0
        symbols_with_befday = 0
        symbols_with_fbtot = 0
        symbols_with_gort = 0
        symbols_with_sma63 = 0
        
        # Track missing fields
        missing_fields = Counter()
        
        # Sample symbols (top 5 with most complete data)
        sample_symbols = []
        
        for symbol in all_symbols:
            snapshot = all_snapshots.get(symbol)
            mdc_data = market_data_cache.get(symbol, {})
            
            # 🟢 FAST PATH: Get data from DataFabric (Single Source of Truth)
            fabric_snapshot = None
            fabric = get_data_fabric()
            if fabric:
                fabric_snapshot = fabric.get_fast_snapshot(symbol)
            
            # Check live prices (from DataFabric OR snapshot OR market_data_cache)
            has_live_prices_fabric = (
                fabric_snapshot and
                fabric_snapshot.get('bid') is not None and
                fabric_snapshot.get('ask') is not None and
                fabric_snapshot.get('last') is not None
            )
            
            has_live_prices_snapshot = (
                snapshot and
                snapshot.bid is not None and
                snapshot.ask is not None and
                snapshot.last is not None
            )
            has_live_prices_cache = (
                mdc_data.get('bid') is not None and
                mdc_data.get('ask') is not None and
                (mdc_data.get('last') is not None or mdc_data.get('price') is not None)
            )
            has_live_prices = has_live_prices_fabric or has_live_prices_snapshot or has_live_prices_cache
            
            if has_live_prices:
                symbols_with_live_prices += 1
            else:
                missing_fields['live_prices'] += 1
            
            # Check prev_close (from snapshot OR market_data_cache OR static data)
            has_prev_close_snapshot = snapshot and snapshot.prev_close is not None and snapshot.prev_close > 0
            has_prev_close_cache = mdc_data.get('prev_close') is not None and mdc_data.get('prev_close', 0) > 0
            
            # Also check static data (CSV) as fallback
            has_prev_close_static = False
            if static_store:
                try:
                    static_data = static_store.get_static_data(symbol)
                    if static_data:
                        prev_close_static = static_data.get('prev_close')
                        if prev_close_static:
                            try:
                                prev_close_float = float(prev_close_static)
                                has_prev_close_static = prev_close_float > 0
                            except (ValueError, TypeError):
                                pass
                except Exception:
                    pass
            
            has_prev_close = has_prev_close_snapshot or has_prev_close_cache or has_prev_close_static
            if has_prev_close:
                symbols_with_prev_close += 1
            else:
                missing_fields['prev_close'] += 1
            
            # Check befday
            has_befday = (
                snapshot and
                snapshot.befday_qty is not None and
                snapshot.befday_cost is not None
            )
            if has_befday:
                symbols_with_befday += 1
            else:
                missing_fields['befday'] += 1
            
            # Check fbtot (from DataFabric - keyed as 'Fbtot')
            # Fallback to snapshot.fbtot if not in fabric
            has_fbtot_fabric = fabric_snapshot and fabric_snapshot.get('Fbtot') is not None
            has_fbtot_snapshot = snapshot and snapshot.fbtot is not None
            
            if has_fbtot_fabric or has_fbtot_snapshot:
                symbols_with_fbtot += 1
            else:
                missing_fields['fbtot'] += 1
            
            # Check gort
            has_gort = snapshot and snapshot.gort is not None
            if has_gort:
                symbols_with_gort += 1
            else:
                missing_fields['gort'] += 1
            
            # Check sma63
            has_sma63 = snapshot and snapshot.sma63_chg is not None
            if has_sma63:
                symbols_with_sma63 += 1
            else:
                missing_fields['sma63_chg'] += 1
            
            # Collect sample (if has most fields)
            if snapshot and has_live_prices and has_prev_close and has_fbtot:
                completeness_score = sum([
                    has_live_prices,
                    has_prev_close,
                    has_befday,
                    has_fbtot,
                    has_gort,
                    has_sma63
                ])
                sample_symbols.append({
                    'symbol': symbol,
                    'completeness': completeness_score,
                    'snapshot': snapshot
                })
        
        # Sort by completeness (highest first)
        sample_symbols.sort(key=lambda x: x['completeness'], reverse=True)
        
        # Get top 5 sample symbols
        top5_samples = []
        for item in sample_symbols[:5]:
            snapshot = item['snapshot']
            top5_samples.append({
                'symbol': item['symbol'],
                'bid': snapshot.bid,
                'ask': snapshot.ask,
                'last': snapshot.last,
                'spread': snapshot.spread,
                'spread_percent': snapshot.spread_percent,
                'prev_close': snapshot.prev_close,
                'befday_qty': snapshot.befday_qty,
                'befday_cost': snapshot.befday_cost,
                'fbtot': snapshot.fbtot,
                'gort': snapshot.gort,
                'sma63_chg': snapshot.sma63_chg
            })
        
        # Market snapshot store ready?
        market_snapshot_store_ready = snapshot_store is not None and len(all_snapshots) > 0
        
        # Missing fields top 10
        missing_fields_top10 = dict(missing_fields.most_common(10))
        
        report = {
            'market_snapshot_store_ready': market_snapshot_store_ready,
            'total_symbols': len(all_symbols),
            'symbols_with_snapshots': len(all_snapshots),
            'symbols_with_live_prices': symbols_with_live_prices,
            'symbols_with_prev_close': symbols_with_prev_close,
            'symbols_with_befday': symbols_with_befday,
            'symbols_with_fbtot': symbols_with_fbtot,
            'symbols_with_gort': symbols_with_gort,
            'symbols_with_sma63': symbols_with_sma63,
            'missing_fields_top10': missing_fields_top10,
            'sample_symbols_top5': top5_samples
        }
        
        logger.debug(f"[DATA_READINESS] Check complete: {symbols_with_live_prices} symbols with live prices")
        
        return report
    
    def is_ready_for_runall(self, min_symbols_ready: int = 20) -> tuple[bool, Optional[str]]:
        """
        Check if data is ready for RUNALL.
        
        🟢 FAST PATH GATING CONDITIONS ONLY:
        - L1 data: bid, ask, last (minimum symbols)
        - prev_close (minimum symbols)
        - Fbtot (minimum symbols)
        
        🔵 NOT GATING (Algo never waits for these):
        - GOD ❌
        - ROD ❌
        - GRPAN ❌
        - SMA63 ❌ (optional filter, not gating)
        - GORT ❌ (optional filter, not gating)
        
        Args:
            min_symbols_ready: Minimum number of symbols with L1 data (default: 20)
            
        Returns:
            (is_ready, reason) tuple
        
        NOTE: Default reduced from 50 to 20 to allow RUNALL to start faster.
        In production, this can be increased via config.
        """
        report = self.check_data_readiness()
        
        # Log current status (FAST PATH metrics only)
        logger.info(
            f"[DATA_READINESS] 🟢 FAST PATH Status: "
            f"L1_prices={report['symbols_with_live_prices']}, "
            f"prev_close={report['symbols_with_prev_close']}, "
            f"fbtot={report['symbols_with_fbtot']} "
            f"(min required: {min_symbols_ready}) "
            f"| 🔵 SLOW PATH (not gating): gort={report['symbols_with_gort']}, sma63={report['symbols_with_sma63']}"
        )
        
        # =====================================================================
        # 🟢 FAST PATH GATING CONDITIONS
        # =====================================================================
        
        # Check minimum symbols with L1 prices (FAST PATH - GATING)
        if report['symbols_with_live_prices'] < min_symbols_ready:
            reason = (
                f"DATA_NOT_READY: Only {report['symbols_with_live_prices']} symbols with L1 prices "
                f"(minimum: {min_symbols_ready})"
            )
            return False, reason
        
        # Check minimum symbols with prev_close (FAST PATH - GATING, relaxed)
        min_prev_close = max(10, min_symbols_ready // 2)
        if report['symbols_with_prev_close'] < min_prev_close:
            reason = (
                f"DATA_NOT_READY: Only {report['symbols_with_prev_close']} symbols with prev_close "
                f"(minimum: {min_prev_close})"
            )
            return False, reason
        
        # Check minimum symbols with fbtot (FAST PATH - GATING, relaxed)
        min_fbtot = max(10, min_symbols_ready // 2)
        if report['symbols_with_fbtot'] < min_fbtot:
            reason = (
                f"DATA_NOT_READY: Only {report['symbols_with_fbtot']} symbols with fbtot "
                f"(minimum: {min_fbtot})"
            )
            return False, reason
        
        # =====================================================================
        # 🔵 SLOW PATH - NOT GATING (Algo never waits for these)
        # =====================================================================
        # GOD, ROD, GRPAN, SMA63, GORT are NOT checked here
        # They are optional for Deeper Analysis only
        # Algo can run without them
        
        return True, None


# Global instance
_data_readiness_checker: Optional[DataReadinessChecker] = None


def get_data_readiness_checker() -> Optional[DataReadinessChecker]:
    """Get global DataReadinessChecker instance"""
    return _data_readiness_checker


def initialize_data_readiness_checker():
    """Initialize global DataReadinessChecker instance"""
    global _data_readiness_checker
    _data_readiness_checker = DataReadinessChecker()
    logger.info("DataReadinessChecker initialized")


