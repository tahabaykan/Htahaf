"""
Janall Derived Metrics Engine v1
Computes all Janall scoring metrics from live Hammer data + CSV static data.

Metrics computed:
- Basic live (spread, mid)
- Passive prices (pf_bid_buy, pf_ask_sell, pf_front_buy, etc.)
- Cheapness/Expensiveness scores (benchmark relative)
- Final scores (FinalBB, FinalFB, FinalAS, FinalFS, FinalSAS, FinalSFS)
- GORT (group relative trend)
- Fbtot, SFStot (group rank + ratio)

Note: GRPAN, BGGG, ETF Cardinal are stubbed for future implementation.
"""

from typing import Dict, Any, Optional, List
from collections import defaultdict
from app.core.logger import logger
from app.market_data.grouping import resolve_group_key
from app.market_data.benchmark_engine import BenchmarkEngine, get_benchmark_engine


class JanallMetricsEngine:
    """
    Computes Janall-derived metrics for symbols.
    """
    
    def __init__(self):
        # Use singleton BenchmarkEngine (config loaded ONCE at startup)
        self.benchmark_engine = get_benchmark_engine()
        
        # Group stats cache (updated in batch)
        self.group_stats_cache: Dict[str, Dict[str, Any]] = {}  # {group_key: stats}
        self.group_stats_cache_time: float = 0.0
        
        # Symbol metrics cache (updated in batch)
        self.symbol_metrics_cache: Dict[str, Dict[str, Any]] = {}  # {symbol: metrics}
        
        # Stub flags for future features
        self.grpan_enabled = False  # TODO: Requires tick data store
        self.bggg_enabled = False  # TODO: Requires tick data store
        self.etf_cardinal_enabled = False  # TODO: Requires time-series store
    
    def _safe_float(self, value: Any, default: float = 0.0) -> float:
        """Safely convert value to float"""
        if value is None or value == 'N/A' or value == '':
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    
    def compute_symbol_metrics(
        self,
        symbol: str,
        static_row: Dict[str, Any],
        live_row: Dict[str, Any],
        benchmark_row: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compute all metrics for a single symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR format)
            static_row: Static data row from CSV
            live_row: Live market data (bid, ask, last, etc.)
            benchmark_row: Benchmark change data
        
        Args:
            symbol: Symbol (PREF_IBKR)
            static_row: Static CSV data
            live_row: Live Hammer market data (must include prev_close)
            benchmark_row: Benchmark change data from BenchmarkEngine
            
        Returns:
            Dict with all computed metrics (explainable with breakdowns)
        """
        try:
            # Extract inputs
            bid = self._safe_float(live_row.get('bid'))
            ask = self._safe_float(live_row.get('ask'))
            last = self._safe_float(live_row.get('last') or live_row.get('price'))
            prev_close = self._safe_float(live_row.get('prev_close'))
            
            final_thg = self._safe_float(static_row.get('FINAL_THG'))
            short_final = self._safe_float(static_row.get('SHORT_FINAL'))
            sma63chg = self._safe_float(static_row.get('SMA63 chg') or static_row.get('SMA63chg'))
            sma246chg = self._safe_float(static_row.get('SMA246 chg') or static_row.get('SMA246chg'))
            
            benchmark_chg = benchmark_row.get('benchmark_chg')
            benchmark_chg_percent = benchmark_row.get('benchmark_chg_percent')
            benchmark_symbol = benchmark_row.get('benchmark_symbol', 'PFF')
            
            # Resolve group key
            group_key = resolve_group_key(static_row)
            
            # A) Basic live metrics
            spread = None
            mid = None
            if bid > 0 and ask > 0:
                spread = ask - bid
                mid = (ask + bid) / 2
            
            # B) Passive prices
            pf_bid_buy = None
            pf_ask_sell = None
            pf_front_buy = None
            pf_front_sell = None
            pf_bid_sell = None
            pf_ask_buy = None
            
            if spread is not None and spread > 0:
                if bid > 0:
                    pf_bid_buy = bid + (spread * 0.15)
                    pf_bid_sell = bid - 0.01
                if ask > 0:
                    pf_ask_sell = ask - (spread * 0.15)
                    pf_ask_buy = ask + 0.01
            
            if last > 0:
                pf_front_buy = last + 0.01
                pf_front_sell = last - 0.01
            
            # C) Ucuzluk/Pahalılık scores (benchmark relative)
            # Calculate changes from prev_close
            pf_bid_buy_chg = None
            pf_ask_sell_chg = None
            pf_front_buy_chg = None
            pf_front_sell_chg = None
            pf_bid_sell_chg = None
            pf_ask_buy_chg = None
            
            if prev_close > 0:
                if pf_bid_buy is not None:
                    pf_bid_buy_chg = pf_bid_buy - prev_close
                if pf_ask_sell is not None:
                    pf_ask_sell_chg = pf_ask_sell - prev_close
                if pf_front_buy is not None:
                    pf_front_buy_chg = pf_front_buy - prev_close
                if pf_front_sell is not None:
                    pf_front_sell_chg = pf_front_sell - prev_close
                if pf_bid_sell is not None:
                    pf_bid_sell_chg = pf_bid_sell - prev_close
                if pf_ask_buy is not None:
                    pf_ask_buy_chg = pf_ask_buy - prev_close
            
            # Calculate cheapness/expensiveness (relative to benchmark)
            bid_buy_ucuzluk = None
            ask_sell_pahalilik = None
            front_buy_ucuzluk = None
            front_sell_pahalilik = None
            bid_sell_pahalilik = None
            ask_buy_ucuzluk = None
            
            if benchmark_chg is not None:
                if pf_bid_buy_chg is not None:
                    bid_buy_ucuzluk = pf_bid_buy_chg - benchmark_chg
                if pf_ask_sell_chg is not None:
                    ask_sell_pahalilik = pf_ask_sell_chg - benchmark_chg
                if pf_front_buy_chg is not None:
                    front_buy_ucuzluk = pf_front_buy_chg - benchmark_chg
                if pf_front_sell_chg is not None:
                    front_sell_pahalilik = pf_front_sell_chg - benchmark_chg
                if pf_bid_sell_chg is not None:
                    bid_sell_pahalilik = pf_bid_sell_chg - benchmark_chg
                if pf_ask_buy_chg is not None:
                    ask_buy_ucuzluk = pf_ask_buy_chg - benchmark_chg
            
            # D) Final scores (800 coefficient)
            final_bb = None
            final_fb = None
            final_as = None
            final_fs = None
            final_sas = None
            final_sfs = None
            
            # JANALL FORMULA: Final = Base - 1000 * ucuzluk/pahalilik (NOT 800!)
            if final_thg > 0:
                if bid_buy_ucuzluk is not None:
                    final_bb = final_thg - (1000 * bid_buy_ucuzluk)
                if front_buy_ucuzluk is not None:
                    final_fb = final_thg - (1000 * front_buy_ucuzluk)
                else:
                    # Debug: final_thg > 0 but front_buy_ucuzluk is None
                    if symbol not in getattr(self, '_final_fb_debug_logged', set()):
                        if not hasattr(self, '_final_fb_debug_logged'):
                            self._final_fb_debug_logged = set()
                        self._final_fb_debug_logged.add(symbol)
                        
                        reasons = []
                        reasons.append("front_buy_ucuzluk=None")
                        if benchmark_chg is None:
                            reasons.append("(benchmark_chg=None)")
                        if pf_front_buy_chg is None:
                            reasons.append("(pf_front_buy_chg=None)")
                            if last is None or last <= 0:
                                reasons.append("(last=None or <=0)")
                            if prev_close is None or prev_close <= 0:
                                reasons.append("(prev_close=None or <=0)")
                        
                        logger.debug(f"🔍 [FINAL_FB_DEBUG] {symbol}: final_fb=None (final_thg={final_thg} > 0) - {', '.join(reasons)}")
                if ask_sell_pahalilik is not None:
                    final_as = final_thg - (1000 * ask_sell_pahalilik)
                if front_sell_pahalilik is not None:
                    final_fs = final_thg - (1000 * front_sell_pahalilik)
            else:
                # Debug: Log why final_fb cannot be calculated (only for first few symbols)
                if symbol not in getattr(self, '_final_fb_debug_logged', set()):
                    if not hasattr(self, '_final_fb_debug_logged'):
                        self._final_fb_debug_logged = set()
                    self._final_fb_debug_logged.add(symbol)
                    
                    reasons = []
                    if final_thg <= 0:
                        reasons.append(f"final_thg <= 0: {final_thg}")
                    if front_buy_ucuzluk is None:
                        reasons.append("front_buy_ucuzluk=None")
                        # Check why front_buy_ucuzluk is None
                        if benchmark_chg is None:
                            reasons.append("(benchmark_chg=None)")
                        if pf_front_buy_chg is None:
                            reasons.append("(pf_front_buy_chg=None)")
                            if last is None or last <= 0:
                                reasons.append("(last=None or <=0)")
                            if prev_close is None or prev_close <= 0:
                                reasons.append("(prev_close=None or <=0)")
                    
                    if reasons:
                        logger.debug(f"🔍 [FINAL_FB_DEBUG] {symbol}: final_fb=None - {', '.join(reasons)}")
            
            if short_final > 0:
                if ask_sell_pahalilik is not None:
                    final_sas = short_final - (1000 * ask_sell_pahalilik)
                if front_sell_pahalilik is not None:
                    final_sfs = short_final - (1000 * front_sell_pahalilik)
            
            # E) GORT (will be computed in apply_group_overlays)
            # F) Fbtot/SFStot (will be computed in apply_group_overlays)
            
            # Build result with explainable breakdowns
            result = {
                # Store symbol for debug logging
                '_symbol': symbol,
                # Group info
                'group_key': group_key,
                'benchmark_symbol': benchmark_symbol,
                'benchmark_chg': benchmark_chg,
                'benchmark_chg_percent': benchmark_chg_percent,
                
                # Basic live
                'spread': round(spread, 4) if spread is not None else None,
                'mid': round(mid, 4) if mid is not None else None,
                
                # Passive prices
                'pf_bid_buy': round(pf_bid_buy, 4) if pf_bid_buy is not None else None,
                'pf_ask_sell': round(pf_ask_sell, 4) if pf_ask_sell is not None else None,
                'pf_front_buy': round(pf_front_buy, 4) if pf_front_buy is not None else None,
                'pf_front_sell': round(pf_front_sell, 4) if pf_front_sell is not None else None,
                'pf_bid_sell': round(pf_bid_sell, 4) if pf_bid_sell is not None else None,
                'pf_ask_buy': round(pf_ask_buy, 4) if pf_ask_buy is not None else None,
                
                # Ucuzluk/Pahalılık scores
                'bid_buy_ucuzluk': round(bid_buy_ucuzluk, 4) if bid_buy_ucuzluk is not None else None,
                'ask_sell_pahalilik': round(ask_sell_pahalilik, 4) if ask_sell_pahalilik is not None else None,
                'front_buy_ucuzluk': round(front_buy_ucuzluk, 4) if front_buy_ucuzluk is not None else None,
                'front_sell_pahalilik': round(front_sell_pahalilik, 4) if front_sell_pahalilik is not None else None,
                'bid_sell_pahalilik': round(bid_sell_pahalilik, 4) if bid_sell_pahalilik is not None else None,
                'ask_buy_ucuzluk': round(ask_buy_ucuzluk, 4) if ask_buy_ucuzluk is not None else None,
                
                # Final scores
                'final_bb': round(final_bb, 2) if final_bb is not None else None,
                'final_fb': round(final_fb, 2) if final_fb is not None else None,
                'final_as': round(final_as, 2) if final_as is not None else None,
                'final_fs': round(final_fs, 2) if final_fs is not None else None,
                'final_sas': round(final_sas, 2) if final_sas is not None else None,
                'final_sfs': round(final_sfs, 2) if final_sfs is not None else None,
                
                # Explainable breakdowns (for Inspector)
                '_breakdown': {
                    'inputs': {
                        'bid': bid,
                        'ask': ask,
                        'last': last,
                        'prev_close': prev_close,
                        'final_thg': final_thg,
                        'short_final': short_final,
                        'sma63chg': sma63chg,
                        'sma246chg': sma246chg,
                        'benchmark_chg': benchmark_chg
                    },
                    'passive_price_calcs': {
                        'pf_bid_buy': f"{bid} + ({spread} * 0.15)" if spread and bid else None,
                        'pf_ask_sell': f"{ask} - ({spread} * 0.15)" if spread and ask else None,
                        'pf_front_buy': f"{last} + 0.01" if last else None,
                        'pf_front_sell': f"{last} - 0.01" if last else None
                    },
                    'final_score_calcs': {
                        'final_bb': f"{final_thg} - (1000 * {bid_buy_ucuzluk})" if final_thg and bid_buy_ucuzluk is not None else None,
                        'final_fb': f"{final_thg} - (1000 * {front_buy_ucuzluk})" if final_thg and front_buy_ucuzluk is not None else None,
                        'final_as': f"{final_thg} - (1000 * {ask_sell_pahalilik})" if final_thg and ask_sell_pahalilik is not None else None,
                        'final_fs': f"{final_thg} - (1000 * {front_sell_pahalilik})" if final_thg and front_sell_pahalilik is not None else None
                    }
                },
                
                # Stubs for future features
                'grpan': None,  # TODO: Requires tick data store
                'bggg_ayrisma': None,  # TODO: Requires tick data store
                'etf_cardinal_status': None  # TODO: Requires time-series store
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error computing metrics for {symbol}: {e}", exc_info=True)
            return {
                'group_key': None,
                'benchmark_symbol': 'PFF',
                'benchmark_chg': None,
                'benchmark_chg_percent': None,
                'error': str(e)
            }
    
    def compute_group_metrics(
        self,
        all_symbols_metrics: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Compute group-level statistics from all symbols' metrics.
        
        Args:
            all_symbols_metrics: List of metric dicts from compute_symbol_metrics
            
        Returns:
            Dict mapping group_key -> group statistics
        """
        try:
            # Group symbols by group_key
            groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for metrics in all_symbols_metrics:
                group_key = metrics.get('group_key')
                if group_key:
                    groups[group_key].append(metrics)
            
            group_stats = {}
            
            for group_key, group_metrics in groups.items():
                # Calculate group averages for SMA63chg and SMA246chg
                sma63chg_values = []
                sma246chg_values = []
                
                # Calculate group averages for FinalFB and FinalSFS (JANALL uses Final_FB for Fbtot, Final_SFS for SFStot)
                final_fb_values = []
                final_sfs_values = []
                # Also collect Fbtot and SFStot values for rank computation
                fbtot_values = []
                sfstot_values = []
                
                for metrics in group_metrics:
                    # Get SMA values from breakdown (or from static data if available)
                    breakdown = metrics.get('_breakdown', {})
                    inputs = breakdown.get('inputs', {})
                    sma63chg = inputs.get('sma63chg')
                    sma246chg = inputs.get('sma246chg')
                    
                    if sma63chg is not None:
                        sma63chg_values.append(sma63chg)
                    if sma246chg is not None:
                        sma246chg_values.append(sma246chg)
                    
                    # Get FinalFB and FinalSFS (JANALL uses Final_FB for Fbtot, Final_SFS for SFStot)
                    # JANALL LOGIC: Exclude N/A values (None, 0, negative, or invalid)
                    # Only include valid positive values for group average calculation
                    final_fb = metrics.get('final_fb')
                    final_sfs = metrics.get('final_sfs')
                    
                    # Exclude N/A: Only include valid positive values (Janall excludes N/A/0/negative)
                    if final_fb is not None and isinstance(final_fb, (int, float)) and final_fb > 0:
                        # Additional check: not NaN or infinite
                        if final_fb == final_fb and final_fb != float('inf') and final_fb != float('-inf'):
                            final_fb_values.append(final_fb)
                    if final_sfs is not None and isinstance(final_sfs, (int, float)) and final_sfs > 0:
                        # Additional check: not NaN or infinite
                        if final_sfs == final_sfs and final_sfs != float('inf') and final_sfs != float('-inf'):
                            final_sfs_values.append(final_sfs)
                    
                    # Get Fbtot and SFStot (after apply_group_overlays, these will be available)
                    fbtot = metrics.get('fbtot')
                    sfstot = metrics.get('sfstot')
                    
                    if fbtot is not None:
                        fbtot_values.append(fbtot)
                    if sfstot is not None:
                        sfstot_values.append(sfstot)
                
                # Calculate averages
                group_avg_sma63 = sum(sma63chg_values) / len(sma63chg_values) if sma63chg_values else None
                group_avg_sma246 = sum(sma246chg_values) / len(sma246chg_values) if sma246chg_values else None
                group_avg_final_fb = sum(final_fb_values) / len(final_fb_values) if final_fb_values else None
                group_avg_final_sfs = sum(final_sfs_values) / len(final_sfs_values) if final_sfs_values else None
                
                group_stats[group_key] = {
                    'symbol_count': len(group_metrics),
                    'group_avg_sma63': round(group_avg_sma63, 4) if group_avg_sma63 is not None else None,
                    'group_avg_sma246': round(group_avg_sma246, 4) if group_avg_sma246 is not None else None,
                    'group_avg_final_fb': round(group_avg_final_fb, 2) if group_avg_final_fb is not None else None,
                    'group_avg_final_sfs': round(group_avg_final_sfs, 2) if group_avg_final_sfs is not None else None,
                    'final_fb_values': final_fb_values,  # For ranking (JANALL uses Final_FB for Fbtot)
                    'final_sfs_values': final_sfs_values  # For ranking (JANALL uses Final_SFS for SFStot)
                }
            
            # Debug: Log group stats summary
            groups_with_fb = sum(1 for s in group_stats.values() if s.get('group_avg_final_fb') is not None and len(s.get('final_fb_values', [])) > 0)
            groups_without_fb = len(group_stats) - groups_with_fb
            total_fb_values = sum(len(s.get('final_fb_values', [])) for s in group_stats.values())
            
            groups_with_sfs = sum(1 for s in group_stats.values() if s.get('group_avg_final_sfs') is not None and len(s.get('final_sfs_values', [])) > 0)
            groups_without_sfs = len(group_stats) - groups_with_sfs
            total_sfs_values = sum(len(s.get('final_sfs_values', [])) for s in group_stats.values())
            
            logger.info(
                f"Computed group stats for {len(group_stats)} groups | "
                f"Groups with valid FB: {groups_with_fb} (without: {groups_without_fb}) | "
                f"Total valid final_fb values: {total_fb_values} | "
                f"Groups with valid SFS: {groups_with_sfs} (without: {groups_without_sfs}) | "
                f"Total valid final_sfs values: {total_sfs_values}"
            )
            
            # Log groups without valid FB/SFS for debugging
            if groups_without_fb > 0:
                groups_missing_fb = [gk for gk, s in group_stats.items() 
                                    if s.get('group_avg_final_fb') is None or len(s.get('final_fb_values', [])) == 0]
                logger.debug(f"Groups without valid FB: {groups_missing_fb[:10]}")  # First 10
                
            if groups_without_sfs > 0:
                groups_missing_sfs = [gk for gk, s in group_stats.items() 
                                     if s.get('group_avg_final_sfs') is None or len(s.get('final_sfs_values', [])) == 0]
                logger.debug(f"Groups without valid SFS: {groups_missing_sfs[:10]}")  # First 10
            return group_stats
            
        except Exception as e:
            logger.error(f"Error computing group metrics: {e}", exc_info=True)
            return {}
    
    def apply_group_overlays(
        self,
        symbol_metrics: Dict[str, Any],
        group_stats: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Apply group-based overlays (GORT, Fbtot, SFStot) to symbol metrics.
        
        Args:
            symbol_metrics: Single symbol's metrics from compute_symbol_metrics
            group_stats: Group statistics from compute_group_metrics
            
        Returns:
            Updated symbol_metrics with GORT, Fbtot, SFStot added
        """
        try:
            group_key = symbol_metrics.get('group_key')
            if not group_key or group_key not in group_stats:
                # No group stats available
                symbol_metrics['gort'] = None
                symbol_metrics['fbtot'] = None
                symbol_metrics['sfstot'] = None
                return symbol_metrics
            
            stats = group_stats[group_key]
            breakdown = symbol_metrics.get('_breakdown', {})
            inputs = breakdown.get('inputs', {})
            
            sma63chg = inputs.get('sma63chg')
            sma246chg = inputs.get('sma246chg')
            group_avg_sma63 = stats.get('group_avg_sma63')
            group_avg_sma246 = stats.get('group_avg_sma246')
            
            # E) GORT calculation
            gort = None
            if (sma63chg is not None and sma246chg is not None and 
                group_avg_sma63 is not None and group_avg_sma246 is not None):
                gort = (0.25 * (sma63chg - group_avg_sma63)) + (0.75 * (sma246chg - group_avg_sma246))
                symbol_metrics['gort'] = round(gort, 4)
            else:
                symbol_metrics['gort'] = None
            
            # F) Fbtot calculation - JANALL ACTUAL CODE (BIREBIR):
            # JANALL uses Final_FB (NOT Final_BB) and weighted sum: (FBPlagr * 0.5) + (FBRatgr * 1.5)
            # FBPlagr = Grup içinde Final FB'ye göre sıralama pozisyonu (rank / total_count)
            # FBRatgr = Final FB / Grup Ortalama Final FB
            final_fb = symbol_metrics.get('final_fb')  # JANALL uses Final_FB, not Final_BB!
            group_avg_final_fb = stats.get('group_avg_final_fb')
            final_fb_values = stats.get('final_fb_values', [])
            
            # Debug logging for FBTOT calculation
            symbol = symbol_metrics.get('_symbol', 'UNKNOWN')
            group_key = symbol_metrics.get('group_key', 'UNKNOWN')
            
            fbtot = None
            # JANALL LOGIC: Fbtot requires valid final_fb, valid group average, and at least 1 valid value in group
            # JANALL LOGIC REQUIREMENT (UPDATED):
            # User selected "BALANCED" Scenario (1.0 Rank + 1.0 Ratio).
            if (final_fb is not None and isinstance(final_fb, (int, float)) and final_fb > 0 and
                final_fb == final_fb and final_fb != float('inf') and final_fb != float('-inf') and
                group_avg_final_fb is not None and isinstance(group_avg_final_fb, (int, float)) and group_avg_final_fb > 0 and
                len(final_fb_values) > 0):
                
                # Previous logic was 0.5/1.5. Now we use 1.0/1.0.
                # Therefore, we incorporate the NEW weights INTO the component definitions:
                # FBPlagr = (Rank / Total) * 1.0
                # FBRatgr = (Score / Avg) * 1.0
                
                # 1. FBPlagr (Weighted Rank)
                # Count how many are <= current (Percentile-like)
                rank = sum(1 for v in final_fb_values if v <= final_fb)
                total_count = len(final_fb_values)
                raw_fbplagr = rank / total_count if total_count > 0 else 0
                
                # Apply 1.0 Weight (Balanced)
                fbplagr = raw_fbplagr * 1.0
                
                # 2. FBRatgr (Weighted Ratio)
                raw_fbratgr = final_fb / group_avg_final_fb
                
                # Apply 1.0 Weight (Balanced)
                fbratgr = raw_fbratgr * 1.0
                
                # 3. Fbtot (Simple Sum)
                fbtot = fbplagr + fbratgr
                
                symbol_metrics['fbtot'] = round(fbtot, 4)
                symbol_metrics['_breakdown']['fbtot_calc'] = {
                    'raw_fbplagr': round(raw_fbplagr, 4),
                    'raw_fbratgr': round(raw_fbratgr, 4),
                    'fbplagr_weighted': round(fbplagr, 4),
                    'fbratgr_weighted': round(fbratgr, 4),
                    'rank': rank,
                    'total_count': total_count,
                    'final_fb': final_fb,
                    'group_avg_final_fb': group_avg_final_fb,
                    'formula': 'Fbtot = FBPlagr(1.0) + FBRatgr(1.0) [Balanced]'
                }
            else:
                symbol_metrics['fbtot'] = None
                # Debug: Log why FBTOT is None
                debug_count_key = f'_fbtot_debug_count_{symbol}'
                debug_count = getattr(self, debug_count_key, 0)
                
                if debug_count < 5:
                    setattr(self, debug_count_key, debug_count + 1)
                    reasons = ["(Conditions not met)"] 
                    logger.warning(f"🔍 [FBTOT_DEBUG] {symbol}: FBTOT=None")
            
            # SFStot calculation - Same Logic (Weights inside components)
            final_sfs = symbol_metrics.get('final_sfs')
            group_avg_final_sfs = stats.get('group_avg_final_sfs')
            final_sfs_values = stats.get('final_sfs_values', [])
            
            sfstot = None
            if (final_sfs is not None and isinstance(final_sfs, (int, float)) and final_sfs > 0 and
                final_sfs == final_sfs and final_sfs != float('inf') and final_sfs != float('-inf') and
                group_avg_final_sfs is not None and isinstance(group_avg_final_sfs, (int, float)) and group_avg_final_sfs > 0 and
                len(final_sfs_values) > 0):
                
                # 1. SFSPlagr (Weighted Rank)
                # Count how many are <= current (Percentile-like)
                rank = sum(1 for v in final_sfs_values if v <= final_sfs)
                total_count = len(final_sfs_values)
                raw_sfsplagr = rank / total_count if total_count > 0 else 0
                
                # Apply 1.0 Weight (Balanced)
                sfsplagr = raw_sfsplagr * 1.0
                
                # 2. SFSRatgr (Weighted Ratio)
                raw_sfsratgr = final_sfs / group_avg_final_sfs
                
                # Apply 1.0 Weight (Balanced)
                sfsratgr = raw_sfsratgr * 1.0
                
                # 3. SFStot (Simple Sum)
                sfstot = sfsplagr + sfsratgr
                
                symbol_metrics['sfstot'] = round(sfstot, 4)
                symbol_metrics['_breakdown']['sfstot_calc'] = {
                    'raw_sfsplagr': round(raw_sfsplagr, 4),
                    'raw_sfsratgr': round(raw_sfsratgr, 4),
                    'sfsplagr_weighted': round(sfsplagr, 4),
                    'sfsratgr_weighted': round(sfsratgr, 4),
                    'rank': rank,
                    'total_count': total_count,
                    'final_sfs': final_sfs,
                    'group_avg_final_sfs': group_avg_final_sfs,
                    'formula': 'SFStot = SFSPlagr(1.0) + SFSRatgr(1.0) [Balanced]'
                }
            
            # Add GORT breakdown
            if gort is not None:
                symbol_metrics['_breakdown']['gort_calc'] = {
                    'sma63chg': sma63chg,
                    'sma246chg': sma246chg,
                    'group_avg_sma63': group_avg_sma63,
                    'group_avg_sma246': group_avg_sma246,
                    'formula': f"0.25*({sma63chg} - {group_avg_sma63}) + 0.75*({sma246chg} - {group_avg_sma246})"
                }
            
            return symbol_metrics
            
        except Exception as e:
            logger.error(f"Error applying group overlays: {e}", exc_info=True)
            return symbol_metrics
    
    def compute_batch_metrics(
        self,
        symbols: List[str],
        static_store,
        market_data_cache: Dict[str, Dict[str, Any]],
        etf_data_store: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Compute metrics for all symbols in batch (called every 2 seconds).
        
        Args:
            symbols: List of symbols to compute metrics for
            static_store: StaticDataStore instance
            market_data_cache: Live market data cache
            etf_data_store: ETF market data store
            
        Returns:
            Dict mapping symbol -> metrics dict
        """
        try:
            # Step 1: Compute individual symbol metrics
            all_symbols_metrics = []
            symbol_metrics_map = {}
            
            for symbol in symbols:
                static_data = static_store.get_static_data(symbol)
                if not static_data:
                    continue
                
                live_data = market_data_cache.get(symbol, {})
                if not live_data:
                    continue
                
                # Get benchmark data
                benchmark_data = self.benchmark_engine.get_benchmark_for_symbol(
                    symbol, 
                    etf_data_store,
                    static_data=static_data
                )
                
                # Compute symbol metrics
                metrics = self.compute_symbol_metrics(symbol, static_data, live_data, benchmark_data)
                all_symbols_metrics.append(metrics)
                symbol_metrics_map[symbol] = metrics
            
            # Step 2: Compute group statistics (before overlays, for FinalBB/FinalSAS)
            group_stats = self.compute_group_metrics(all_symbols_metrics)
            
            # Step 3: Apply group overlays (GORT, Fbtot, SFStot)
            for symbol, metrics in symbol_metrics_map.items():
                updated_metrics = self.apply_group_overlays(metrics, group_stats)
                symbol_metrics_map[symbol] = updated_metrics
            
            # Step 4: Recompute group stats to include Fbtot/SFStot values
            # Now that overlays are applied, we can collect fbtot/sfstot values
            for group_key, stats in group_stats.items():
                fbtot_values = []
                sfstot_values = []
                for symbol, metrics in symbol_metrics_map.items():
                    if metrics.get('group_key') == group_key:
                        fbtot = metrics.get('fbtot')
                        sfstot = metrics.get('sfstot')
                        if fbtot is not None:
                            fbtot_values.append(fbtot)
                        if sfstot is not None:
                            sfstot_values.append(sfstot)
                stats['fbtot_values'] = fbtot_values
                stats['sfstot_values'] = sfstot_values
            
            # Step 5: Update caches
            self.group_stats_cache = group_stats
            import time
            self.group_stats_cache_time = time.time()
            self.symbol_metrics_cache = symbol_metrics_map
            
            logger.debug(f"Computed batch metrics for {len(symbol_metrics_map)} symbols, {len(group_stats)} groups")
            return symbol_metrics_map
            
        except Exception as e:
            logger.error(f"Error in batch metrics computation: {e}", exc_info=True)
            return {}


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_janall_metrics_engine_instance: Optional[JanallMetricsEngine] = None

def get_janall_metrics_engine() -> Optional[JanallMetricsEngine]:
    """Get singleton instance of JanallMetricsEngine"""
    global _janall_metrics_engine_instance
    if _janall_metrics_engine_instance is None:
        try:
            _janall_metrics_engine_instance = JanallMetricsEngine()
            logger.info("JanallMetricsEngine initialized")
        except Exception as e:
            logger.error(f"Failed to initialize JanallMetricsEngine: {e}")
            return None
    return _janall_metrics_engine_instance

def initialize_janall_metrics_engine() -> Optional[JanallMetricsEngine]:
    """Force initialization of JanallMetricsEngine"""
    return get_janall_metrics_engine()
