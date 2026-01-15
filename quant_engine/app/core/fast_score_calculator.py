"""
FAST SCORE CALCULATOR - L1 + CSV Based Instant Scoring
======================================================

🟢 FAST PATH COMPONENT

This module calculates FAST scores from:
1. L1 Market Data (bid, ask, last) - from Hammer
2. Static CSV Data (prev_close, FINAL_THG, AVG_ADV) - from DataFabric

🎯 CALCULATED SCORES (FAST - no tick-by-tick):
- daily_change (cent): last - prev_close
- benchmark_chg: ETF performance
- spread: ask - bid
- spread_percent: spread / last * 100
- bid_buy_ucuzluk: (bid - prev_close) / prev_close
- ask_sell_pahalilik: (ask - prev_close) / prev_close
- front_buy_ucuzluk: bid_buy_ucuzluk - benchmark_chg
- front_sell_pahalilik: ask_sell_pahalilik - benchmark_chg
- Final_BB_skor: FINAL_THG - 1000 * bid_buy_ucuzluk
- Final_FB_skor: FINAL_THG - 1000 * front_buy_ucuzluk
- Final_SAS_skor: SHORT_FINAL + 1000 * ask_sell_pahalilik
- Final_SFS_skor: SHORT_FINAL + 1000 * front_sell_pahalilik

⚠️ DOES NOT CALCULATE (SLOW PATH):
- GOD, ROD, GRPAN (tick-by-tick required)

PERFORMANCE:
- Event-driven: only recalculates when L1 changes
- Batch compute: can process all symbols in <50ms
- No disk I/O: all data from RAM
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import threading

from app.core.logger import logger
from app.core.data_fabric import get_data_fabric


# Group-based metrics (Fbtot, SFStot, GORT) are calculated by JanallMetricsEngine
# We import it lazily to avoid circular imports
def _get_janall_metrics_engine():
    """Lazy import JanallMetricsEngine"""
    try:
        from app.market_data.janall_metrics_engine import JanallMetricsEngine
        return JanallMetricsEngine()
    except ImportError:
        return None


class FastScoreCalculator:
    """
    Fast Score Calculator - calculates FAST PATH scores from L1 + CSV.
    
    🟢 FAST PATH - No tick-by-tick, instant calculation.
    """
    
    _instance: Optional['FastScoreCalculator'] = None
    _lock = threading.Lock()
    
    # Default ETF for benchmark (SPY for US equities)
    DEFAULT_BENCHMARK_ETF = 'SPY'
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._benchmark_etf = self.DEFAULT_BENCHMARK_ETF
        self._last_compute_time: Optional[datetime] = None
        self._compute_count = 0
        self._initialized = True
        logger.info("🚀 FastScoreCalculator initialized (FAST PATH)")
    
    def set_benchmark_etf(self, etf_symbol: str) -> None:
        """Set benchmark ETF for relative calculations"""
        self._benchmark_etf = etf_symbol
        logger.info(f"📊 Benchmark ETF set to: {etf_symbol}")
    
    def compute_fast_scores(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Compute FAST PATH scores for a single symbol.
        
        🟢 FAST PATH - Uses only L1 + CSV data.
        
        🔑 CRITICAL: symbol MUST be in PREF_IBKR format (e.g., "RLJ PRA")
        This ensures key consistency with DataFabric.
        
        Args:
            symbol: PREF_IBKR symbol (display format, e.g., "RLJ PRA")
            
        Returns:
            Dict with calculated FAST scores or None if data missing
        """
        fabric = get_data_fabric()
        
        # Get static data (from CSV - already in RAM)
        static = fabric.get_static(symbol)
        if not static:
            return None
        
        # Get live data (from Hammer L1 - already in RAM)
        live = fabric.get_live(symbol)
        if not live:
            return None
        
        # Extract required fields
        bid = live.get('bid')
        ask = live.get('ask')
        last = live.get('last')
        
        prev_close = static.get('prev_close')
        final_thg = static.get('FINAL_THG')
        short_final = static.get('SHORT_FINAL')
        
        # Validate required fields for calculation
        if bid is None or ask is None or last is None:
            return None
        if prev_close is None or prev_close <= 0:
            return None
        
        # Convert to float
        try:
            bid = float(bid)
            ask = float(ask)
            last = float(last)
            prev_close = float(prev_close)
            final_thg = float(final_thg) if final_thg is not None else 0.0
            short_final = float(short_final) if short_final is not None else 0.0
        except (ValueError, TypeError):
            return None
        
        # =====================================================================
        # FAST SCORE CALCULATIONS (Janall formulas - EXACT COPY)
        # =====================================================================
        
        # Basic metrics
        daily_change = last - prev_close  # In cents
        spread = ask - bid if ask > 0 and bid > 0 else 0.0
        spread_percent = (spread / last * 100) if last > 0 else 0.0
        
        # =====================================================================
        # PASSIVE FİYATLAR (Janall formülleri - Ntahaf)
        # =====================================================================
        pf_bid_buy = bid + (spread * 0.15) if bid > 0 else 0.0
        pf_front_buy = last + 0.01 if last > 0 else 0.0
        pf_ask_buy = ask + 0.01 if ask > 0 else 0.0
        pf_ask_sell = ask - (spread * 0.15) if ask > 0 else 0.0
        pf_front_sell = last - 0.01 if last > 0 else 0.0
        pf_bid_sell = bid - 0.01 if bid > 0 else 0.0
        
        # =====================================================================
        # DEĞİŞİMLER (pf_*_chg = pf_* - prev_close)
        # =====================================================================
        pf_bid_buy_chg = pf_bid_buy - prev_close if prev_close > 0 else 0.0
        pf_front_buy_chg = pf_front_buy - prev_close if prev_close > 0 else 0.0
        pf_ask_buy_chg = pf_ask_buy - prev_close if prev_close > 0 else 0.0
        pf_ask_sell_chg = pf_ask_sell - prev_close if prev_close > 0 else 0.0
        pf_front_sell_chg = pf_front_sell - prev_close if prev_close > 0 else 0.0
        pf_bid_sell_chg = pf_bid_sell - prev_close if prev_close > 0 else 0.0
        
        # Get benchmark type (from CGRUP) and change (ETF performance)
        # Janall logic: CGRUP varsa CGRUP kullan, yoksa DEFAULT
        cgrup = static.get('CGRUP')
        benchmark_type = self._get_benchmark_type(cgrup)
        benchmark_chg = self._get_benchmark_change(fabric, benchmark_type, static=static)
        
        # =====================================================================
        # UCUZLUK/PAHALILIK SKORLARI (benchmark'dan sonra)
        # =====================================================================
        bid_buy_ucuzluk = pf_bid_buy_chg - benchmark_chg
        front_buy_ucuzluk = pf_front_buy_chg - benchmark_chg
        ask_buy_ucuzluk = pf_ask_buy_chg - benchmark_chg
        ask_sell_pahalilik = pf_ask_sell_chg - benchmark_chg
        front_sell_pahalilik = pf_front_sell_chg - benchmark_chg
        bid_sell_pahalilik = pf_bid_sell_chg - benchmark_chg
        
        # =====================================================================
        # FINAL SKORLAR (Janall formula: multiplier = 800)
        # =====================================================================
        # Final_BB = FINAL_THG - 800 * bid_buy_ucuzluk
        # Lower bid_buy_ucuzluk (more negative = cheaper) → Higher Final_BB
        
        def final_skor(final_thg, skor):
            """Final skor hesaplama - 1000 katsayısı ile (Janall - BIREBIR)"""
            return final_thg - 1000 * skor
        
        final_bb_skor = final_skor(final_thg, bid_buy_ucuzluk)
        final_fb_skor = final_skor(final_thg, front_buy_ucuzluk)
        final_ab_skor = final_skor(final_thg, ask_buy_ucuzluk)
        final_as_skor = final_skor(final_thg, ask_sell_pahalilik)
        final_fs_skor = final_skor(final_thg, front_sell_pahalilik)
        final_bs_skor = final_skor(final_thg, bid_sell_pahalilik)
        
        # Short Final skorları (SHORT_FINAL kullanarak - çıkarma formülü)
        final_sas_skor = short_final - 800 * ask_sell_pahalilik if short_final > 0 else 0.0
        final_sfs_skor = short_final - 800 * front_sell_pahalilik if short_final > 0 else 0.0
        final_sbs_skor = short_final - 800 * bid_sell_pahalilik if short_final > 0 else 0.0
        
        # Build result (Janall format - EXACT COPY)
        result = {
            # Basic metrics
            'daily_change': daily_change,
            'spread': spread,
            'spread_percent': spread_percent,
            
            # Ucuzluk/Pahalilik scores (Janall format)
            'Bid_buy_ucuzluk_skoru': round(bid_buy_ucuzluk, 2),
            'Front_buy_ucuzluk_skoru': round(front_buy_ucuzluk, 2),
            'Ask_buy_ucuzluk_skoru': round(ask_buy_ucuzluk, 2),
            'Ask_sell_pahalilik_skoru': round(ask_sell_pahalilik, 2),
            'Front_sell_pahalilik_skoru': round(front_sell_pahalilik, 2),
            'Bid_sell_pahalilik_skoru': round(bid_sell_pahalilik, 2),
            
            # Legacy aliases (for compatibility)
            'bid_buy_ucuzluk': bid_buy_ucuzluk,
            'front_buy_ucuzluk': front_buy_ucuzluk,
            'ask_buy_ucuzluk': ask_buy_ucuzluk,
            'ask_sell_pahalilik': ask_sell_pahalilik,
            'front_sell_pahalilik': front_sell_pahalilik,
            'bid_sell_pahalilik': bid_sell_pahalilik,
            
            # Benchmark
            'Benchmark_Type': benchmark_type,  # Frontend expects Benchmark_Type
            'benchmark_type': benchmark_type,  # Legacy
            'Benchmark_Chg': round(benchmark_chg, 4),  # Frontend expects Benchmark_Chg
            'benchmark_chg': benchmark_chg,  # Legacy
            
            # Final Scores (Janall format - 800 katsayısı)
            'Final_BB_skor': round(final_bb_skor, 2),
            'Final_FB_skor': round(final_fb_skor, 2),
            'Final_AB_skor': round(final_ab_skor, 2),
            'Final_AS_skor': round(final_as_skor, 2),
            'Final_FS_skor': round(final_fs_skor, 2),
            'Final_BS_skor': round(final_bs_skor, 2),
            'Final_SAS_skor': round(final_sas_skor, 2),
            'Final_SFS_skor': round(final_sfs_skor, 2),
            'Final_SBS_skor': round(final_sbs_skor, 2),
            
            # Spread (Janall format)
            'Spread': round(spread, 4),
            
            # Metadata
            '_computed_at': datetime.now(),
            '_is_fast_path': True,
        }
        
        return result
    
    def compute_all_fast_scores(self, include_group_metrics: bool = True) -> Dict[str, Dict[str, Any]]:
        """
        Compute FAST PATH scores for ALL symbols.
        
        🟢 FAST PATH - Batch computation, no tick-by-tick.
        
        Args:
            include_group_metrics: If True, also compute Fbtot/SFStot/GORT via JanallMetricsEngine
        
        Returns:
            Dict of {symbol: scores}
        """
        fabric = get_data_fabric()
        start_time = datetime.now()
        
        # Get all symbols with static data
        all_symbols = fabric.get_all_static_symbols()
        
        results = {}
        computed = 0
        skipped = 0
        
        # Phase 1: Compute basic FAST scores (L1 + CSV)
        debug_printed = 0
        for symbol in all_symbols:
            scores = self.compute_fast_scores(symbol)
            if scores:
                results[symbol] = scores
                computed += 1
            else:
                skipped += 1

        
        # Phase 2: Compute group-based metrics (Fbtot, SFStot, GORT)
        # These require all symbols to be processed first for ranking
        if include_group_metrics and computed > 0:
            group_metrics = self._compute_group_based_metrics(all_symbols, results)
            
            # Merge group metrics into results
            for symbol, metrics in group_metrics.items():
                if symbol in results:
                    results[symbol].update({
                        'Fbtot': metrics.get('fbtot'),
                        'SFStot': metrics.get('sfstot'),
                        'GORT': metrics.get('gort'),
                    })
        
        # Phase 3: Update DataFabric with all computed scores
        for symbol, scores in results.items():
            fabric.update_derived(symbol, scores)
        
        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
        self._last_compute_time = datetime.now()
        self._compute_count += 1
        
        logger.info(
            f"🚀 [FAST_SCORES] Batch compute: {computed} symbols in {elapsed_ms:.1f}ms "
            f"(skipped: {skipped}, group_metrics: {include_group_metrics})"
        )
        
        return results
    
    def _compute_group_based_metrics(
        self, 
        all_symbols: List[str], 
        basic_scores: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Compute group-based metrics (Fbtot, SFStot, GORT).
        
        These metrics require:
        1. All symbols to be processed first (for ranking within group)
        2. Group assignments from static data
        
        🟢 FAST PATH - No tick-by-tick, uses pre-computed Final_BB/Final_SFS scores.
        """
        fabric = get_data_fabric()
        results = {}
        
        try:
            # Prepare data for JanallMetricsEngine
            janall_engine = _get_janall_metrics_engine()
            if not janall_engine:
                logger.warning("JanallMetricsEngine not available for group metrics")
                return results
            
            # Build input for batch computation
            all_metrics_list = []
            for symbol in all_symbols:
                static = fabric.get_static(symbol)
                live = fabric.get_live(symbol)
                basic = basic_scores.get(symbol, {})
                
                if not static or not live:
                    continue
                
                # Build metrics dict compatible with JanallMetricsEngine
                # JANALL uses Final_FB for Fbtot and Final_SFS for SFStot
                metrics = {
                    'symbol': symbol,
                    'group_key': static.get('GROUP') or static.get('CGRUP'),
                    'final_bb': basic.get('Final_BB_skor'),  # Keep for reference
                    'final_fb': basic.get('Final_FB_skor'),  # JANALL uses this for Fbtot
                    'final_sas': basic.get('Final_SAS_skor'),  # Keep for reference
                    'final_sfs': basic.get('Final_SFS_skor'),  # JANALL uses this for SFStot
                    '_breakdown': {
                        'inputs': {
                            'sma63chg': static.get('SMA63 chg'),
                            'sma246chg': static.get('SMA246 chg'),
                        }
                    }
                }
                all_metrics_list.append(metrics)
            
            if not all_metrics_list:
                return results
            
            # Compute group stats
            group_stats = janall_engine.compute_group_metrics(all_metrics_list)
            
            # Apply group overlays to each symbol
            for metrics in all_metrics_list:
                symbol = metrics.get('symbol')
                updated = janall_engine.apply_group_overlays(metrics, group_stats)
                results[symbol] = {
                    'fbtot': updated.get('fbtot'),
                    'sfstot': updated.get('sfstot'),
                    'gort': updated.get('gort'),
                }
            
            logger.debug(f"🚀 [FAST_SCORES] Group metrics computed for {len(results)} symbols")
            
        except Exception as e:
            logger.error(f"Error computing group metrics: {e}", exc_info=True)
        
        return results
    
    def compute_dirty_symbols(self) -> Dict[str, Dict[str, Any]]:
        """
        Compute FAST scores only for dirty (changed) symbols.
        
        🟢 FAST PATH - Event-driven, only recalculate what changed.
        
        Returns:
            Dict of {symbol: scores} for dirty symbols
        """
        fabric = get_data_fabric()
        dirty_symbols = fabric.get_dirty_symbols()
        
        if not dirty_symbols:
            return {}
        
        start_time = datetime.now()
        results = {}
        
        for symbol in dirty_symbols:
            scores = self.compute_fast_scores(symbol)
            if scores:
                results[symbol] = scores
                fabric.update_derived(symbol, scores)
        
        elapsed_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        if results:
            logger.debug(
                f"🚀 [FAST_SCORES] Dirty compute: {len(results)} symbols in {elapsed_ms:.1f}ms"
            )
        
        return results
    
    def _get_benchmark_type(self, cgrup: Optional[str]) -> str:
        """
        Get benchmark type from CGRUP (Janall logic).
        
        Args:
            cgrup: CGRUP value from static data (e.g., "C525", "5.25", or None)
            
        Returns:
            Benchmark type key (e.g., "C525", "DEFAULT")
        """
        if not cgrup:
            return 'DEFAULT'
        
        try:
            cgrup_str = str(cgrup).strip()
            if not cgrup_str or cgrup_str.lower() == 'nan':
                return 'DEFAULT'
            
            # CGRUP değerini benchmark key'e çevir (Janall logic)
            if cgrup_str.lower().startswith('c'):
                benchmark_key = cgrup_str.upper()  # 'c525' -> 'C525'
            else:
                # Eski format: sayısal değer (5.25 -> C525)
                try:
                    numeric_value = float(cgrup_str)
                    benchmark_key = f"C{int(numeric_value * 100)}"
                except (ValueError, TypeError):
                    return 'DEFAULT'
            
            # Validate benchmark key exists in benchmark formulas
            # For now, return the key (validation happens in benchmark engine)
            return benchmark_key
            
        except Exception:
            return 'DEFAULT'
    
    def _get_benchmark_change(self, fabric, benchmark_type: str = 'DEFAULT', static: Optional[Dict[str, Any]] = None) -> float:
        """
        Get benchmark ETF change (for front_buy/sell calculations) - Janall logic.
        
        Uses BenchmarkEngine to calculate benchmark change based on CGRUP.
        
        Args:
            fabric: DataFabric instance
            benchmark_type: Benchmark type (e.g., "C525", "DEFAULT")
            static: Static data (optional, for group resolution)
        
        Returns:
            Benchmark change as decimal (e.g., 0.01 = 1%)
        """
        try:
            from app.market_data.benchmark_engine import BenchmarkEngine
            from app.market_data.grouping import resolve_primary_group, resolve_secondary_group
            
            # Get BenchmarkEngine instance
            from app.market_data.benchmark_engine import get_benchmark_engine
            benchmark_engine = get_benchmark_engine()
            
            # Resolve primary and secondary groups from static data (Janall logic)
            primary_group = None
            secondary_group = None
            
            if static:
                primary_group = resolve_primary_group(static)
                secondary_group = resolve_secondary_group(static, primary_group or "")
            
            # For kuponlu groups, use CGRUP (secondary_group) if available
            # For other groups, ignore CGRUP and use primary group formula
            # If benchmark_type is DEFAULT and we have a CGRUP, use it
            if benchmark_type != 'DEFAULT' and secondary_group:
                # Use the benchmark_type (CGRUP) as secondary_group
                secondary_group = benchmark_type.lower()  # e.g., "C525" -> "c525"
            
            # Get benchmark formula (ETF weights) based on two-tier grouping
            formula = benchmark_engine.get_benchmark_formula(
                static_data=static,
                primary_group=primary_group,
                secondary_group=secondary_group
            )
            
            if not formula:
                return 0.0
            
            # Calculate weighted benchmark change
            benchmark_change = 0.0
            for etf_symbol, coefficient in formula.items():
                if coefficient == 0:
                    continue
                
                # Get ETF change
                etf_live = fabric.get_etf_live(etf_symbol)
                etf_prev_close = fabric.get_etf_prev_close(etf_symbol)
                
                if not etf_live or not etf_prev_close:
                    continue
                
                etf_last = etf_live.get('last')
                if etf_last is None or etf_prev_close <= 0:
                    continue
                
                try:
                    etf_change = (float(etf_last) - float(etf_prev_close)) / float(etf_prev_close)
                    contribution = etf_change * coefficient
                    benchmark_change += contribution
                except (ValueError, TypeError, ZeroDivisionError):
                    continue
            
            # Round to 4 decimals (Janall logic)
            return round(benchmark_change, 4)
            
        except Exception as e:
            logger.warning(f"Error calculating benchmark change: {e}")
            return 0.0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get calculator statistics"""
        return {
            'benchmark_etf': self._benchmark_etf,
            'last_compute_time': self._last_compute_time.isoformat() if self._last_compute_time else None,
            'compute_count': self._compute_count,
        }


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_fast_score_calculator: Optional[FastScoreCalculator] = None


def get_fast_score_calculator() -> FastScoreCalculator:
    """Get global FastScoreCalculator instance (singleton)"""
    global _fast_score_calculator
    if _fast_score_calculator is None:
        _fast_score_calculator = FastScoreCalculator()
    return _fast_score_calculator


def compute_fast_scores_for_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Convenience function to compute FAST scores for a symbol.
    
    🔑 CRITICAL: symbol MUST be in PREF_IBKR format (e.g., "RLJ PRA")
    This ensures key consistency with DataFabric.
    
    Args:
        symbol: PREF_IBKR symbol (display format, e.g., "RLJ PRA")
    """
    # 🔑 KEY CONSISTENCY: Ensure symbol is in PREF_IBKR format
    symbol = str(symbol).strip()
    return get_fast_score_calculator().compute_fast_scores(symbol)


def compute_all_fast_scores(include_group_metrics: bool = True) -> Dict[str, Dict[str, Any]]:
    """Convenience function to compute FAST scores for all symbols"""
    return get_fast_score_calculator().compute_all_fast_scores(include_group_metrics=include_group_metrics)


def compute_dirty_fast_scores() -> Dict[str, Dict[str, Any]]:
    """Convenience function to compute FAST scores for dirty symbols"""
    return get_fast_score_calculator().compute_dirty_symbols()

