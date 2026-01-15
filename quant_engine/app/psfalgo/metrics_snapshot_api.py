"""
Metrics Snapshot API - Production-Grade

Provides async metrics snapshot API for PSFALGO decision engines.
Aggregates data from market_data_cache, GRPAN, RWVAP, pricing_overlay, and static data.
This is the SINGLE entry point for decision engines to get all metrics.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from app.core.logger import logger
from app.psfalgo.decision_models import SymbolMetrics
from app.market_data.static_data_store import StaticDataStore


@dataclass
class MetricsSnapshotAPI:
    """
    Metrics Snapshot API - async, production-grade.
    
    Responsibilities:
    - Aggregate metrics from multiple sources
    - Provide single entry point for decision engines
    - Ensure consistency (same cycle, same data)
    - Handle missing data gracefully
    """
    
    def __init__(
        self,
        market_data_cache: Optional[Dict[str, Dict[str, Any]]] = None,
        static_store: Optional[StaticDataStore] = None,
        grpan_engine=None,
        rwvap_engine=None,
        pricing_overlay_engine=None,
        janall_metrics_engine=None
    ):
        """
        Initialize Metrics Snapshot API.
        
        Args:
            market_data_cache: Market data cache {symbol: market_data}
            static_store: StaticDataStore instance
            grpan_engine: GRPANEngine instance
            rwvap_engine: RWVAPEngine instance
            pricing_overlay_engine: PricingOverlayEngine instance
            janall_metrics_engine: JanallMetricsEngine instance
        """
        self.market_data_cache = market_data_cache or {}
        self.static_store = static_store
        self.grpan_engine = grpan_engine
        self.rwvap_engine = rwvap_engine
        self.pricing_overlay_engine = pricing_overlay_engine
        self.janall_metrics_engine = janall_metrics_engine
    
    async def get_metrics_snapshot(
        self,
        symbols: List[str],
        snapshot_ts: Optional[datetime] = None
    ) -> Dict[str, SymbolMetrics]:
        """
        Get metrics snapshot for symbols.
        
        This is the SINGLE entry point for decision engines.
        All metrics are aggregated here to ensure consistency.
        
        Args:
            symbols: List of symbols to get metrics for
            snapshot_ts: Snapshot timestamp (for consistency). If None, uses now.
            
        Returns:
            Dict mapping symbol -> SymbolMetrics
        """
        if snapshot_ts is None:
            snapshot_ts = datetime.now()
        
        snapshot = {}
        
        for symbol in symbols:
            try:
                metrics = await self._aggregate_metrics_for_symbol(symbol, snapshot_ts)
                if metrics:
                    snapshot[symbol] = metrics
            except Exception as e:
                logger.error(f"Error getting metrics for {symbol}: {e}", exc_info=True)
                # Continue with other symbols
        
        logger.debug(f"Metrics snapshot: {len(snapshot)}/{len(symbols)} symbols")
        return snapshot
    
    async def _aggregate_metrics_for_symbol(
        self,
        symbol: str,
        snapshot_ts: datetime
    ) -> Optional[SymbolMetrics]:
        """
        Aggregate all metrics for a single symbol.
        
        PHASE 7: Now uses MarketSnapshot as single source of truth.
        Falls back to legacy aggregation if MarketSnapshot not available.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            snapshot_ts: Snapshot timestamp
            
        Returns:
            SymbolMetrics object or None if no data available
        """
        # PHASE 7: Try to get from MarketSnapshot first (single source of truth)
        from app.psfalgo.market_snapshot_store import get_market_snapshot_store
        
        snapshot_store = get_market_snapshot_store()
        if snapshot_store:
            market_snapshot = snapshot_store.get_current_snapshot(symbol)
            if market_snapshot:
                # Get additional metrics (GRPAN, RWVAP, Pricing Overlay)
                grpan_metrics = self._get_grpan_metrics(symbol)
                rwvap_metrics = self._get_rwvap_metrics(symbol)
                overlay_metrics = self._get_pricing_overlay_metrics(symbol)
                
                # Get static data for final_thg, short_final
                static_data = None
                if self.static_store:
                    static_data = self.static_store.get_static_data(symbol)
                
                # Convert MarketSnapshot to SymbolMetrics
                return SymbolMetrics(
                    symbol=symbol,
                    timestamp=snapshot_ts,
                    
                    # Pricing (from MarketSnapshot)
                    bid=market_snapshot.bid,
                    ask=market_snapshot.ask,
                    last=market_snapshot.last,
                    prev_close=market_snapshot.prev_close,
                    spread=market_snapshot.spread,
                    spread_percent=market_snapshot.spread_percent,
                    
                    # GRPAN (still from grpan_engine - can be enhanced later)
                    grpan_price=grpan_metrics.get('grpan_price'),
                    grpan_concentration_percent=grpan_metrics.get('concentration_percent'),
                    grpan_ort_dev=grpan_metrics.get('grpan_ort_dev'),
                    
                    # RWVAP (still from rwvap_engine - can be enhanced later)
                    rwvap_1d=rwvap_metrics.get('rwvap_1d'),
                    rwvap_ort_dev=rwvap_metrics.get('rwvap_ort_dev'),
                    
                    # Janall Metrics (from MarketSnapshot)
                    fbtot=market_snapshot.fbtot,
                    sfstot=market_snapshot.sfstot,
                    gort=market_snapshot.gort,
                    sma63_chg=market_snapshot.sma63_chg,
                    sma246_chg=market_snapshot.sma246_chg,
                    
                    # Pricing Overlay (still from pricing_overlay_engine - can be enhanced later)
                    bid_buy_ucuzluk=overlay_metrics.get('Bid_buy_ucuzluk_skoru'),
                    ask_sell_pahalilik=overlay_metrics.get('Ask_sell_pahalilik_skoru'),
                    front_buy_ucuzluk=overlay_metrics.get('Front_buy_ucuzluk_skoru'),
                    front_sell_pahalilik=overlay_metrics.get('Front_sell_pahalilik_skoru'),
                    
                    # Static (from MarketSnapshot + static_store)
                    avg_adv=market_snapshot.avg_adv,
                    final_thg=self._safe_float(static_data.get('FINAL_THG')) if static_data else None,
                    short_final=self._safe_float(static_data.get('SHORT_FINAL')) if static_data else None,
                    maxalw=int(static_data.get('MAXALW', 2000)) if static_data else 2000,
                    
                    # JFIN Scores - GET FROM PRICING_OVERLAY_ENGINE (already calculated LIVE)
                    # PricingOverlayEngine calculates these using Janall formula:
                    # Final_BB = FINAL_THG - 1000 * bid_buy_ucuzluk
                    final_bb_skor=self._safe_float(overlay_metrics.get('Final_BB_skor')),
                    final_fb_skor=self._safe_float(overlay_metrics.get('Final_FB_skor')),
                    final_sas_skor=self._safe_float(overlay_metrics.get('Final_SAS_skor')),
                    final_sfs_skor=self._safe_float(overlay_metrics.get('Final_SFS_skor')),
                )
        
        # Fallback to legacy aggregation (backward compatibility)
        # Get market data
        market_data = self.market_data_cache.get(symbol, {})
        
        # Get static data
        static_data = None
        if self.static_store:
            static_data = self.static_store.get_static_data(symbol)
        
        # Get GRPAN metrics
        grpan_metrics = self._get_grpan_metrics(symbol)
        
        # Get RWVAP metrics
        rwvap_metrics = self._get_rwvap_metrics(symbol)
        
        # Get pricing overlay metrics
        overlay_metrics = self._get_pricing_overlay_metrics(symbol)
        
        # Get Janall metrics
        janall_metrics = self._get_janall_metrics(symbol)
        
        # Aggregate into SymbolMetrics
        metrics = SymbolMetrics(
            symbol=symbol,
            timestamp=snapshot_ts,
            
            # Pricing (from market_data_cache)
            bid=self._safe_float(market_data.get('bid')),
            ask=self._safe_float(market_data.get('ask')),
            last=self._safe_float(market_data.get('last')) or self._safe_float(market_data.get('price')),
            prev_close=self._safe_float(market_data.get('prev_close')),
            spread=self._safe_float(market_data.get('spread')),
            spread_percent=self._safe_float(market_data.get('spread_percent')),
            
            # GRPAN (from grpan_engine)
            grpan_price=grpan_metrics.get('grpan_price'),
            grpan_concentration_percent=grpan_metrics.get('concentration_percent'),
            grpan_ort_dev=grpan_metrics.get('grpan_ort_dev'),  # GOD
            
            # RWVAP (from rwvap_engine)
            rwvap_1d=rwvap_metrics.get('rwvap_1d'),
            rwvap_ort_dev=rwvap_metrics.get('rwvap_ort_dev'),  # ROD
            
            # Janall Metrics (from janall_metrics_engine)
            fbtot=janall_metrics.get('fbtot'),
            sfstot=janall_metrics.get('sfstot'),
            gort=janall_metrics.get('gort'),
            sma63_chg=janall_metrics.get('sma63_chg'),
            sma246_chg=janall_metrics.get('sma246_chg'),
            
            # Pricing Overlay (from pricing_overlay_engine)
            bid_buy_ucuzluk=overlay_metrics.get('Bid_buy_ucuzluk_skoru'),
            ask_sell_pahalilik=overlay_metrics.get('Ask_sell_pahalilik_skoru'),
            front_buy_ucuzluk=overlay_metrics.get('Front_buy_ucuzluk_skoru'),
            front_sell_pahalilik=overlay_metrics.get('Front_sell_pahalilik_skoru'),
            
            # Static (from static_data_store)
            avg_adv=self._safe_float(static_data.get('AVG_ADV')) if static_data else None,
            final_thg=self._safe_float(static_data.get('FINAL_THG')) if static_data else None,
            short_final=self._safe_float(static_data.get('SHORT_FINAL')) if static_data else None,
            maxalw=int(static_data.get('MAXALW', 2000)) if static_data else 2000,
            
            # JFIN Scores - GET FROM PRICING_OVERLAY_ENGINE (already calculated LIVE)
            # PricingOverlayEngine calculates these using Janall formula:
            # Final_BB = FINAL_THG - 1000 * bid_buy_ucuzluk
            final_bb_skor=self._safe_float(overlay_metrics.get('Final_BB_skor')),
            final_fb_skor=self._safe_float(overlay_metrics.get('Final_FB_skor')),
            final_sas_skor=self._safe_float(overlay_metrics.get('Final_SAS_skor')),
            final_sfs_skor=self._safe_float(overlay_metrics.get('Final_SFS_skor')),
        )
        
        return metrics
    
    def _calculate_final_jfin_score(
        self, 
        base_score: Any, 
        ucuzluk_score: Any, 
        direction: str
    ) -> Optional[float]:
        """
        Calculate JFIN Final Scores LIVE from base scores and ucuzluk/pahalilik.
        
        Janall Formula (CRITICAL: uses 1000 multiplier, not 800!):
        - Final_BB_skor = FINAL_THG - 1000 * bid_buy_ucuzluk
        - Final_FB_skor = FINAL_THG - 1000 * front_buy_ucuzluk
        - Final_SAS_skor = SHORT_FINAL - 1000 * ask_sell_pahalilik
        - Final_SFS_skor = SHORT_FINAL - 1000 * front_sell_pahalilik
        
        Args:
            base_score: FINAL_THG (for long) or SHORT_FINAL (for short)
            ucuzluk_score: Ucuzluk or Pahalilik score
            direction: 'long' or 'short'
            
        Returns:
            Calculated final JFIN score or None if inputs invalid
        """
        try:
            base = self._safe_float(base_score)
            ucuzluk = self._safe_float(ucuzluk_score)
            
            if base is None or ucuzluk is None:
                return None
            
            # Janall formula: Final = Base - 1000 * ucuzluk (JANALL uses 1000!)
            # For shorts, if SHORT_FINAL is 0, return 0
            if direction == 'short' and base == 0:
                return 0.0
            
            return round(base - 1000 * ucuzluk, 2)
        except Exception:
            return None
    
    def _get_grpan_metrics(self, symbol: str) -> Dict[str, Any]:
        """Get GRPAN metrics for symbol"""
        if not self.grpan_engine:
            return {}
        
        try:
            # Get latest GRPAN (backward compatible)
            grpan_data = self.grpan_engine.compute_grpan(symbol)
            if not grpan_data:
                return {}
            
            # Get GRPAN ORT DEV (GOD) - average of all GRPAN windows
            grpan_windows = self.grpan_engine.grpan_cache.get(symbol, {})
            grpan_prices = []
            for window_name, window_data in grpan_windows.items():
                if window_name != 'latest_pan' and window_data and window_data.get('grpan_price'):
                    grpan_prices.append(window_data['grpan_price'])
            
            grpan_ort = sum(grpan_prices) / len(grpan_prices) if grpan_prices else None
            grpan_ort_dev = None
            if grpan_ort and grpan_data.get('grpan_price'):
                # GOD = Last - GRPAN ORT
                last_price = self.market_data_cache.get(symbol, {}).get('last')
                if last_price:
                    grpan_ort_dev = last_price - grpan_ort
            
            return {
                'grpan_price': grpan_data.get('grpan_price'),
                'concentration_percent': grpan_data.get('concentration_percent'),
                'grpan_ort_dev': grpan_ort_dev
            }
        except Exception as e:
            logger.debug(f"Error getting GRPAN metrics for {symbol}: {e}")
            return {}
    
    def _get_rwvap_metrics(self, symbol: str) -> Dict[str, Any]:
        """Get RWVAP metrics for symbol"""
        if not self.rwvap_engine:
            return {}
        
        try:
            # Get RWVAP 1D
            rwvap_1d = self.rwvap_engine.get_rwvap(symbol, window='1D')
            
            # Get RWVAP ORT DEV (ROD) - average of all RWVAP windows
            rwvap_windows = ['1D', '3D', '5D']
            rwvap_prices = []
            for window in rwvap_windows:
                rwvap = self.rwvap_engine.get_rwvap(symbol, window=window)
                if rwvap and rwvap.get('rwvap_price'):
                    rwvap_prices.append(rwvap['rwvap_price'])
            
            rwvap_ort = sum(rwvap_prices) / len(rwvap_prices) if rwvap_prices else None
            rwvap_ort_dev = None
            if rwvap_ort:
                # ROD = Last - RWVAP ORT
                last_price = self.market_data_cache.get(symbol, {}).get('last')
                if last_price:
                    rwvap_ort_dev = last_price - rwvap_ort
            
            return {
                'rwvap_1d': rwvap_1d.get('rwvap_price') if rwvap else None,
                'rwvap_ort_dev': rwvap_ort_dev
            }
        except Exception as e:
            logger.debug(f"Error getting RWVAP metrics for {symbol}: {e}")
            return {}
    
    def _get_pricing_overlay_metrics(self, symbol: str) -> Dict[str, Any]:
        """Get pricing overlay metrics for symbol including JFIN scores"""
        if not self.pricing_overlay_engine:
            return {}
        
        try:
            overlay_scores = self.pricing_overlay_engine.get_overlay_scores(symbol)
            if not overlay_scores or overlay_scores.get('status') != 'OK':
                return {}
            
            return {
                # Ucuzluk/Pahalılık Scores
                'Bid_buy_ucuzluk_skoru': overlay_scores.get('Bid_buy_ucuzluk_skoru'),
                'Ask_sell_pahalilik_skoru': overlay_scores.get('Ask_sell_pahalilik_skoru'),
                'Front_buy_ucuzluk_skoru': overlay_scores.get('Front_buy_ucuzluk_skoru'),
                'Front_sell_pahalilik_skoru': overlay_scores.get('Front_sell_pahalilik_skoru'),
                # JFIN Final Scores (calculated by PricingOverlayEngine)
                'Final_BB_skor': overlay_scores.get('Final_BB_skor'),
                'Final_FB_skor': overlay_scores.get('Final_FB_skor'),
                'Final_SAS_skor': overlay_scores.get('Final_SAS_skor'),
                'Final_SFS_skor': overlay_scores.get('Final_SFS_skor'),
            }
        except Exception as e:
            logger.debug(f"Error getting pricing overlay metrics for {symbol}: {e}")
            return {}
    
    def _get_janall_metrics(self, symbol: str) -> Dict[str, Any]:
        """Get Janall metrics for symbol"""
        if not self.janall_metrics_engine:
            return {}
        
        try:
            # Get Janall metrics from cache
            janall_metrics = self.janall_metrics_engine.get_metrics(symbol)
            if not janall_metrics:
                return {}
            
            return {
                'fbtot': janall_metrics.get('fbtot'),
                'sfstot': janall_metrics.get('sfstot'),
                'gort': janall_metrics.get('gort'),
                'sma63_chg': janall_metrics.get('sma63_chg'),
                'sma246_chg': janall_metrics.get('sma246_chg'),
            }
        except Exception as e:
            logger.debug(f"Error getting Janall metrics for {symbol}: {e}")
            return {}
    
    def _safe_float(self, value: Any) -> Optional[float]:
        """Safely convert value to float"""
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None


# Global instance
_metrics_snapshot_api: Optional[MetricsSnapshotAPI] = None


def get_metrics_snapshot_api() -> Optional[MetricsSnapshotAPI]:
    """Get global MetricsSnapshotAPI instance"""
    return _metrics_snapshot_api


def initialize_metrics_snapshot_api(
    market_data_cache: Optional[Dict[str, Dict[str, Any]]] = None,
    static_store: Optional[StaticDataStore] = None,
    grpan_engine=None,
    rwvap_engine=None,
    pricing_overlay_engine=None,
    janall_metrics_engine=None
):
    """Initialize global MetricsSnapshotAPI instance"""
    global _metrics_snapshot_api
    _metrics_snapshot_api = MetricsSnapshotAPI(
        market_data_cache=market_data_cache,
        static_store=static_store,
        grpan_engine=grpan_engine,
        rwvap_engine=rwvap_engine,
        pricing_overlay_engine=pricing_overlay_engine,
        janall_metrics_engine=janall_metrics_engine
    )
    logger.info("MetricsSnapshotAPI initialized")

