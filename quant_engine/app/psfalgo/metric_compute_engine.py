"""
Metric Compute Engine - Janall-Compatible Metrics

Computes all metrics used by decision engines.
Janall-compatible calculations.

Key Principles:
- SADECE hesaplar
- Karar vermez
- Execution yapmaz
- Decision engine'lerin BEKLEDİĞİ tüm alanlar burada üretilir
"""

from datetime import datetime
from typing import Dict, Any, Optional

from app.core.logger import logger
from app.psfalgo.market_snapshot_models import MarketSnapshot
from app.market_data.static_data_store import get_static_store
from app.market_data.pricing_overlay_engine import get_pricing_overlay_engine

# Lazy import GRPAN/RWVAP to avoid import errors breaking the entire pipeline
def _safe_get_grpan_engine():
    """Safely get GRPAN engine, return None if unavailable"""
    try:
        from app.market_data.grpan_engine import get_grpan_engine
        return get_grpan_engine()
    except Exception as e:
        logger.warning(f"[METRIC] GRPAN_UNAVAILABLE: {e}")
        return None

def _safe_get_rwvap_engine():
    """Safely get RWVAP engine, return None if unavailable"""
    try:
        from app.market_data.rwvap_engine import get_rwvap_engine
        return get_rwvap_engine()
    except Exception as e:
        logger.warning(f"[METRIC] RWVAP_UNAVAILABLE: {e}")
        return None


class MetricComputeEngine:
    """
    Metric Compute Engine - computes all metrics for MarketSnapshot.
    
    Responsibilities:
    - Compute SMA63_CHG, SMA246_CHG
    - Compute FBTOT, SFSTOT, GORT
    - Compute spread, spread_percent
    - Compute befday_* and today_* fields
    
    Does NOT:
    - Make trading decisions
    - Execute orders
    - Modify decision engines
    """
    
    def __init__(self):
        """Initialize Metric Compute Engine"""
        logger.info("MetricComputeEngine initialized")
    
    def compute_metrics(
        self,
        symbol: str,
        market_data: Dict[str, Any],
        position_data: Optional[Dict[str, Any]] = None,
        static_data: Optional[Dict[str, Any]] = None,
        janall_metrics: Optional[Dict[str, Any]] = None
    ) -> MarketSnapshot:
        """
        Compute all metrics for a symbol and create MarketSnapshot.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            market_data: Live market data (bid, ask, last, prev_close)
            position_data: Position data (qty, cost, befday_qty, befday_cost)
            static_data: Static data from CSV (SMA63 chg, SMA246 chg, AVG_ADV, etc.)
            
        Returns:
            MarketSnapshot with all computed metrics
        """
        # Get static data if not provided
        if static_data is None:
            static_store = get_static_store()
            if static_store:
                static_data = static_store.get_static_data(symbol)
        
        # Extract live market data
        bid = market_data.get('bid')
        ask = market_data.get('ask')
        last = market_data.get('last') or market_data.get('price')
        prev_close = market_data.get('prev_close')
        
        # CRITICAL: If prev_close is missing from market_data, try to get it from CSV (DataFabric/StaticDataStore)
        # This ensures MarketSnapshotStore has prev_close for DataReadinessChecker
        if not prev_close or prev_close <= 0:
            try:
                # Try DataFabric first (fastest - already in RAM)
                from app.core.data_fabric import get_data_fabric
                fabric = get_data_fabric()
                if fabric:
                    static_from_fabric = fabric.get_static(symbol)
                    if static_from_fabric and static_from_fabric.get('prev_close'):
                        prev_close = static_from_fabric.get('prev_close')
                        # Update market_data so it's available for rest of computation
                        market_data['prev_close'] = prev_close
            except Exception:
                pass
            
            # Fallback: Try StaticDataStore
            if (not prev_close or prev_close <= 0) and static_data:
                try:
                    prev_close_from_static = static_data.get('prev_close')
                    if prev_close_from_static:
                        try:
                            prev_close = float(prev_close_from_static)
                            if prev_close > 0:
                                # Update market_data so it's available for rest of computation
                                market_data['prev_close'] = prev_close
                        except (ValueError, TypeError):
                            pass
                except Exception:
                    pass
        
        # Calculate spread
        spread = None
        spread_percent = None
        if bid and ask and bid > 0 and ask > 0:
            spread = ask - bid
            mid_price = (bid + ask) / 2
            if mid_price > 0:
                spread_percent = (spread / mid_price) * 100
        
        # Extract position data
        befday_qty = 0.0
        befday_cost = 0.0
        today_qty = 0.0
        today_cost = 0.0
        
        if position_data:
            befday_qty = position_data.get('befday_qty', 0.0)
            befday_cost = position_data.get('befday_cost', 0.0)
            today_qty = position_data.get('qty', 0.0)
            today_cost = position_data.get('cost', 0.0)
        
        # Calculate today changes
        today_qty_chg = today_qty - befday_qty
        
        # Extract static metrics
        sma63_chg = None
        sma246_chg = None
        avg_adv = None
        
        if static_data:
            sma63_chg = static_data.get('SMA63 chg')
            sma246_chg = static_data.get('SMA246 chg')
            avg_adv = static_data.get('AVG_ADV')
        
        # Compute FBTOT, SFSTOT, GORT from JanallMetricsEngine (primary source)
        # JanallMetricsEngine computes these in batch and stores in symbol_metrics_cache
        fbtot = None
        sfstot = None
        gort = None
        
        # Try to get from JanallMetricsEngine cache (computed in batch)
        # Use janall_metrics parameter if provided, otherwise try to get from cache
        if janall_metrics:
            fbtot = janall_metrics.get('fbtot')
            sfstot = janall_metrics.get('sfstot')
            gort = janall_metrics.get('gort')
        else:
            try:
                from app.api.market_data_routes import janall_metrics_engine
                if janall_metrics_engine and hasattr(janall_metrics_engine, 'symbol_metrics_cache'):
                    janall_metrics = janall_metrics_engine.symbol_metrics_cache.get(symbol, {})
                    if janall_metrics:
                        fbtot = janall_metrics.get('fbtot')
                        sfstot = janall_metrics.get('sfstot')
                        gort = janall_metrics.get('gort')
            except Exception as e:
                logger.debug(f"[METRIC] Could not get Janall metrics for {symbol}: {e}")
        
        # CRITICAL: Pricing overlay MUST compute even if GRPAN/RWVAP unavailable
        # Pricing overlay uses: bid/ask/last, benchmark, spread - NO GRPAN dependency
        pricing_overlay = None
        try:
            pricing_overlay = get_pricing_overlay_engine()
        except Exception as e:
            logger.warning(f"[METRIC] Pricing overlay unavailable for {symbol}: {e}")
        
        # CRITICAL: Extract pricing overlay scores and write to snapshot
        # These MUST be populated even if GRPAN unavailable
        bb_ucuz = None
        fb_ucuz = None
        ab_ucuz = None
        as_pahali = None
        fs_pahali = None
        bs_pahali = None
        final_bb = None
        final_fb = None
        final_ab = None
        final_as = None
        final_fs = None
        final_bs = None
        final_sas = None
        benchmark_chg = None
        pricing_mode = None  # Initialize pricing_mode
        
        # Compute pricing overlay scores (bb_ucuz, fb_ucuz, final_fb, final_fs, etc.)
        # These are REQUIRED and MUST work without GRPAN
        if pricing_overlay and static_data:
            try:
                overlay_scores = pricing_overlay.get_overlay_scores(symbol)
                if overlay_scores and overlay_scores.get('status') == 'OK':
                    # Extract all pricing overlay scores
                    bb_ucuz = overlay_scores.get('Bid_buy_ucuzluk_skoru')
                    fb_ucuz = overlay_scores.get('Front_buy_ucuzluk_skoru')
                    ab_ucuz = overlay_scores.get('Ask_buy_ucuzluk_skoru')
                    as_pahali = overlay_scores.get('Ask_sell_pahalilik_skoru')
                    fs_pahali = overlay_scores.get('Front_sell_pahalilik_skoru')
                    bs_pahali = overlay_scores.get('Bid_sell_pahalilik_skoru')
                    
                    # Extract final scores
                    final_bb = overlay_scores.get('Final_BB_skor')
                    final_fb = overlay_scores.get('Final_FB_skor')
                    final_ab = overlay_scores.get('Final_AB_skor')
                    final_as = overlay_scores.get('Final_AS_skor')
                    final_fs = overlay_scores.get('Final_FS_skor')
                    final_bs = overlay_scores.get('Final_BS_skor')
                    final_sas = overlay_scores.get('Final_SAS_skor')
                    
                    # Extract benchmark change and pricing mode
                    benchmark_chg = overlay_scores.get('benchmark_chg')
                    pricing_mode = overlay_scores.get('pricing_mode')  # "RELATIVE" or "ABSOLUTE"
                    
                    # FBTOT fallback from pricing overlay
                    if fb_ucuz is not None and fbtot is None:
                        fbtot = 1.0 + (fb_ucuz / 100.0)
                    
                    # SFSTOT fallback from pricing overlay
                    if fs_pahali is not None and sfstot is None:
                        sfstot = 1.0 + (fs_pahali / 100.0)
            except Exception as e:
                logger.debug(f"[METRIC] Pricing overlay computation failed for {symbol}: {e}")
        
        # GORT fallback: from static data (if available)
        if gort is None and static_data:
            gort = static_data.get('GORT')
        
        # Extract static data fields (FINAL_THG, SHORT_FINAL)
        final_thg = None
        short_final = None
        if static_data:
            final_thg = static_data.get('FINAL_THG')
            short_final = static_data.get('SHORT_FINAL')
        
        # Account type (from position data or config)
        account_type = position_data.get('account_type') if position_data else None
        
        # Create snapshot with ALL pricing overlay scores
        snapshot = MarketSnapshot(
            symbol=symbol,
            bid=bid,
            ask=ask,
            last=last,
            spread=spread,
            spread_percent=spread_percent,
            prev_close=prev_close,
            befday_qty=befday_qty,
            befday_cost=befday_cost,
            today_qty_chg=today_qty_chg,
            today_cost=today_cost,
            sma63_chg=sma63_chg,
            sma246_chg=sma246_chg,
            fbtot=fbtot,
            sfstot=sfstot,
            gort=gort,
            avg_adv=avg_adv,
            # Pricing overlay scores
            bb_ucuz=bb_ucuz,
            fb_ucuz=fb_ucuz,
            ab_ucuz=ab_ucuz,
            as_pahali=as_pahali,
            fs_pahali=fs_pahali,
            bs_pahali=bs_pahali,
            # Final scores
            final_bb=final_bb,
            final_fb=final_fb,
            final_ab=final_ab,
            final_as=final_as,
            final_fs=final_fs,
            final_bs=final_bs,
            final_sas=final_sas,
            # Benchmark and static data
            benchmark_chg=benchmark_chg,
            pricing_mode=pricing_mode,  # NEW: RELATIVE or ABSOLUTE
            final_thg=final_thg,
            short_final=short_final,
            account_type=account_type,
            snapshot_ts=datetime.now()
        )
        
        logger.debug(f"[METRIC] Computed metrics for {symbol}: fbtot={fbtot}, gort={gort}, sma63_chg={sma63_chg}")
        
        return snapshot


# Global instance
_metric_compute_engine: Optional[MetricComputeEngine] = None


def get_metric_compute_engine() -> Optional[MetricComputeEngine]:
    """Get global MetricComputeEngine instance"""
    return _metric_compute_engine


def initialize_metric_compute_engine():
    """Initialize global MetricComputeEngine instance"""
    global _metric_compute_engine
    _metric_compute_engine = MetricComputeEngine()
    logger.info("MetricComputeEngine initialized")

