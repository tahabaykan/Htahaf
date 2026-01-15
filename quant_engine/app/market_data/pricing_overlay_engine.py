"""
Pricing Overlay Engine
Calculates benchmark-aware pricing overlay scores (ucuzluk/pahalılık skorları) matching Janall exactly.

Features:
- Dirty tracking: symbols become dirty when bid/ask/last changes OR benchmark ETFs change
- Throttle mechanism: min 250ms per symbol, batch processing with backpressure
- Score calculation: matches Janall formulas exactly (passive prices, changes, final scores)
"""

import time
from typing import Dict, Any, Optional, Set
from collections import defaultdict
from pathlib import Path
import yaml

from app.core.logger import logger
from app.market_data.benchmark_engine import BenchmarkEngine, get_benchmark_engine
from app.market_data.grouping import resolve_primary_group, resolve_secondary_group


class PricingOverlayEngine:
    """
    Calculates benchmark-aware pricing overlay scores.
    Uses dirty tracking and throttle mechanism to prevent performance degradation.
    """
    
    def __init__(self, benchmark_rules_path: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        """
        Initialize PricingOverlayEngine.
        
        Args:
            benchmark_rules_path: Path to benchmark_rules.yaml (default: app/config/benchmark_rules.yaml)
            config: Optional config dict with compute settings
        """
        # Load benchmark rules
        if benchmark_rules_path is None:
            base_dir = Path(__file__).parent.parent.parent
            benchmark_rules_path = base_dir / "app" / "config" / "benchmark_rules.yaml"
        
        self.benchmark_rules_path = Path(benchmark_rules_path)
        self.benchmark_config = self._load_benchmark_config()
        
        # Initialize benchmark engine (uses benchmark_rules.yaml)
        # Use singleton BenchmarkEngine (config loaded ONCE at startup)
        # Pass Path object, not string, to avoid .exists() error
        self.benchmark_engine = get_benchmark_engine(config_path=str(self.benchmark_rules_path))
        
        # Throttle configuration
        self.config = config or {}
        self.min_interval_ms = self.config.get('min_interval_ms', 250)
        # No batch size limit - process all dirty symbols
        self.batch_size = self.config.get('batch_size', 999999)  # Effectively unlimited
        self.max_queue_size = self.config.get('max_queue_size', 999999)  # Effectively unlimited
        
        # Dirty tracking
        self.dirty_symbols: Set[str] = set()  # Symbols that need recomputation
        self.last_compute_time: Dict[str, float] = {}  # {symbol: last_compute_timestamp}
        self.last_quote: Dict[str, Dict[str, float]] = {}  # {symbol: {bid, ask, last}}
        self.last_benchmark_chg: Dict[str, float] = {}  # {symbol: last_benchmark_chg}
        
        # Symbol -> benchmark ETFs mapping (for dirty tracking when ETFs change)
        self.symbol_benchmark_etfs: Dict[str, Set[str]] = {}  # {symbol: {ETF1, ETF2, ...}}
        
        # Results cache
        self.overlay_cache: Dict[str, Dict[str, Any]] = {}  # {symbol: overlay_scores}
        
        # Performance monitoring
        self.stats = {
            'total_computes': 0,
            'total_time_ms': 0.0,
            'batch_count': 0,
            'max_queue_size_seen': 0
        }
        
        logger.info(f"PricingOverlayEngine initialized (min_interval={self.min_interval_ms}ms, batch_size=unlimited)")
    
    def _load_benchmark_config(self) -> Dict[str, Any]:
        """Load benchmark configuration from YAML file"""
        try:
            if self.benchmark_rules_path.exists():
                with open(self.benchmark_rules_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    logger.info(f"Benchmark rules loaded from {self.benchmark_rules_path}")
                    return config or {}
            else:
                logger.warning(f"Benchmark rules file not found: {self.benchmark_rules_path}")
                return {}
        except Exception as e:
            logger.error(f"Error loading benchmark rules: {e}", exc_info=True)
            return {}
    
    def mark_dirty(self, symbol: str):
        """
        Mark symbol as needing recomputation.
        Called when bid/ask/last changes.
        
        Args:
            symbol: Symbol to mark as dirty
        """
        if symbol:
            self.dirty_symbols.add(symbol)
            logger.debug(f"Marked {symbol} as dirty")
    
    def mark_benchmark_dirty(self, etf_symbol: str):
        """
        Mark all symbols using this ETF as dirty.
        Called when ETF price changes.
        
        Args:
            etf_symbol: ETF symbol that changed (e.g., 'TLT', 'PFF')
        """
        # Find all symbols that use this ETF
        affected_symbols = set()
        for symbol, etf_set in self.symbol_benchmark_etfs.items():
            if etf_symbol in etf_set:
                affected_symbols.add(symbol)
        
        # Mark them as dirty
        for symbol in affected_symbols:
            self.dirty_symbols.add(symbol)
        
        if affected_symbols:
            logger.debug(f"Marked {len(affected_symbols)} symbols as dirty due to {etf_symbol} change")
    
    def compute_overlay_scores(
        self,
        symbol: str,
        static_row: Dict[str, Any],
        live_quote: Dict[str, Any],
        benchmarks_live: Dict[str, Dict[str, Any]],
        benchmarks_prev_close: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Calculate all overlay scores for a symbol (matching Janall exactly).
        
        Args:
            symbol: Symbol (PREF_IBKR)
            static_row: Static data row (must include FINAL_THG, SHORT_FINAL, prev_close)
            live_quote: Live market data {bid, ask, last, prev_close}
            benchmarks_live: Live ETF prices {ETF: {last, ...}}
            benchmarks_prev_close: Previous close for ETFs {ETF: prev_close}
            
        Returns:
            Dict with all overlay scores:
            - benchmark_type: Benchmark type (e.g., 'C450', 'DEFAULT')
            - benchmark_chg: Benchmark change (composite)
            - Bid_buy_ucuzluk_skoru, Front_buy_ucuzluk_skoru, Ask_buy_ucuzluk_skoru
            - Ask_sell_pahalilik_skoru, Front_sell_pahalilik_skoru, Bid_sell_pahalilik_skoru
            - Final_BB_skor, Final_FB_skor, Final_AB_skor, Final_AS_skor, Final_FS_skor, Final_BS_skor
            - Final_SAS_skor, Final_SFS_skor, Final_SBS_skor
            - Spread
        """
        try:
            # Extract values
            bid = float(live_quote.get('bid', 0)) if live_quote.get('bid') else 0
            ask = float(live_quote.get('ask', 0)) if live_quote.get('ask') else 0
            last_price = float(live_quote.get('last', 0)) if live_quote.get('last') else 0
            prev_close = float(live_quote.get('prev_close', 0)) if live_quote.get('prev_close') else 0
            
            # Fallback: try to get prev_close from static_row
            if prev_close <= 0:
                prev_close_raw = static_row.get('prev_close', 0)
                if prev_close_raw and prev_close_raw != 'N/A':
                    try:
                        prev_close = float(prev_close_raw)
                    except (ValueError, TypeError):
                        prev_close = 0
            
            if prev_close <= 0:
                logger.warning(f"{symbol}: prev_close not available, returning COLLECTING state")
                return {
                    'status': 'COLLECTING',
                    'benchmark_type': None,
                    'benchmark_chg': None
                }
            
            # Calculate benchmark change
            # Build ETF data store for benchmark engine
            etf_data_store = {}
            missing_etfs = []
            for etf_symbol, etf_data in benchmarks_live.items():
                etf_last = etf_data.get('last') or etf_data.get('price')
                etf_prev_close = benchmarks_prev_close.get(etf_symbol)
                
                if etf_last is not None and etf_prev_close is not None:
                    etf_data_store[etf_symbol] = {
                        'last': etf_last,
                        'prev_close': etf_prev_close
                    }
                else:
                    missing_etfs.append(f"{etf_symbol}(last={etf_last}, prev_close={etf_prev_close})")
            
            # Debug: Log if ETFs are missing
            if missing_etfs and len(etf_data_store) == 0:
                logger.debug(f"[PRICING_OVERLAY] {symbol}: No ETF data available. Missing: {', '.join(missing_etfs)}")
            
            # Get benchmark change using benchmark engine
            benchmark_result = self.benchmark_engine.compute_benchmark_change(
                etf_data_store=etf_data_store,
                static_data=static_row
            )
            
            benchmark_chg = benchmark_result.get('benchmark_chg')
            benchmark_formula = benchmark_result.get('benchmark_formula', {})
            
            # Debug: Log benchmark_chg calculation
            if benchmark_chg is None:
                logger.debug(
                    f"[PRICING_OVERLAY] {symbol}: benchmark_chg=None. "
                    f"ETF_data_store keys: {list(etf_data_store.keys())}, "
                    f"formula: {benchmark_formula}, "
                    f"benchmark_last: {benchmark_result.get('benchmark_last')}, "
                    f"benchmark_prev_close: {benchmark_result.get('benchmark_prev_close')}"
                )
            
            # Store which ETFs this symbol uses (for dirty tracking)
            self.symbol_benchmark_etfs[symbol] = set(benchmark_formula.keys())
            
            # Get benchmark type from CGRUP (Janall logic: CGRUP varsa CGRUP, yoksa DEFAULT)
            cgrup = static_row.get('CGRUP') or static_row.get('cgrup')
            benchmark_type = 'DEFAULT'
            if cgrup:
                try:
                    cgrup_str = str(cgrup).strip()
                    if cgrup_str and cgrup_str.lower() != 'nan':
                        if cgrup_str.lower().startswith('c'):
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
            
            # Determine pricing mode: RELATIVE (if benchmark available) or ABSOLUTE (if not)
            pricing_mode = "RELATIVE" if benchmark_chg is not None else "ABSOLUTE"
            
            # Calculate spread
            spread = float(ask) - float(bid) if ask != 'N/A' and bid != 'N/A' and ask > 0 and bid > 0 else 0
            
            # Calculate mid price for absolute pricing
            mid_price = (float(bid) + float(ask)) / 2.0 if bid > 0 and ask > 0 else (last_price if last_price > 0 else 0)
            
            # Get GRPAN and RWVAP for absolute pricing (if benchmark not available)
            grpan_price = None
            rwvap_price = None
            
            if pricing_mode == "ABSOLUTE":
                try:
                    # Try to get GRPAN (prefer 1d window, fallback to latest_pan)
                    from app.market_data.grpan_engine import get_grpan_engine
                    grpan_engine = get_grpan_engine()
                    if grpan_engine:
                        grpan_result = grpan_engine.compute_grpan(symbol, 'pan_1d')
                        if not grpan_result or grpan_result.get('status') != 'OK':
                            grpan_result = grpan_engine.compute_grpan(symbol)  # Fallback to latest_pan
                        if grpan_result and grpan_result.get('status') == 'OK':
                            grpan_price = grpan_result.get('grpan_price')
                except Exception as e:
                    logger.debug(f"[PRICING_OVERLAY] Could not get GRPAN for {symbol}: {e}")
                
                try:
                    # Try to get RWVAP (prefer 1d window)
                    from app.market_data.rwvap_engine import get_rwvap_engine
                    rwvap_engine = get_rwvap_engine()
                    if rwvap_engine:
                        rwvap_result = rwvap_engine.compute_rwvap(symbol, 'rwvap_1d')
                        if rwvap_result and rwvap_result.get('status') == 'OK':
                            rwvap_price = rwvap_result.get('rwvap')
                except Exception as e:
                    logger.debug(f"[PRICING_OVERLAY] Could not get RWVAP for {symbol}: {e}")
            
            # Passive prices (matching Janall exactly)
            pf_bid_buy = float(bid) + (spread * 0.15) if bid > 0 else 0
            pf_front_buy = float(last_price) + 0.01 if last_price > 0 else 0
            pf_ask_buy = float(ask) + 0.01 if ask > 0 else 0
            pf_ask_sell = float(ask) - (spread * 0.15) if ask > 0 else 0
            pf_front_sell = float(last_price) - 0.01 if last_price > 0 else 0
            pf_bid_sell = float(bid) - 0.01 if bid > 0 else 0
            
            # Price changes (matching Janall exactly)
            pf_bid_buy_chg = pf_bid_buy - prev_close if prev_close > 0 else 0
            pf_front_buy_chg = pf_front_buy - prev_close if prev_close > 0 else 0
            pf_ask_buy_chg = pf_ask_buy - prev_close if prev_close > 0 else 0
            pf_ask_sell_chg = pf_ask_sell - prev_close if prev_close > 0 else 0
            pf_front_sell_chg = pf_front_sell - prev_close if prev_close > 0 else 0
            pf_bid_sell_chg = pf_bid_sell - prev_close if prev_close > 0 else 0
            
            # Ucuzluk/Pahalılık scores
            if pricing_mode == "RELATIVE":
                # RELATIVE mode: Use benchmark_chg (matching Janall exactly)
                # Note: benchmark_chg is in cents (composite last - composite prev_close)
                bid_buy_ucuzluk = pf_bid_buy_chg - benchmark_chg
                front_buy_ucuzluk = pf_front_buy_chg - benchmark_chg
                ask_buy_ucuzluk = pf_ask_buy_chg - benchmark_chg
                ask_sell_pahalilik = pf_ask_sell_chg - benchmark_chg
                front_sell_pahalilik = pf_front_sell_chg - benchmark_chg
                bid_sell_pahalilik = pf_bid_sell_chg - benchmark_chg
            else:
                # ABSOLUTE mode: Use GRPAN/RWVAP (preferred trading without benchmark)
                # BB_UCUZ = (mid_price - RWVAP) / RWVAP * 100 (percentage)
                # FB_UCUZ = (last - GRPAN) / GRPAN * 100
                # AS_PAHALI = (ask - GRPAN) / GRPAN * 100
                # BS_PAHALI = (bid - GRPAN) / GRPAN * 100
                
                if rwvap_price and rwvap_price > 0:
                    # Bid Buy: (mid - RWVAP) / RWVAP * 100
                    bid_buy_ucuzluk = ((mid_price - rwvap_price) / rwvap_price) * 100 if mid_price > 0 else 0
                else:
                    bid_buy_ucuzluk = 0
                
                if grpan_price and grpan_price > 0:
                    # Front Buy: (last - GRPAN) / GRPAN * 100
                    front_buy_ucuzluk = ((last_price - grpan_price) / grpan_price) * 100 if last_price > 0 else 0
                    # Ask Buy: (ask - GRPAN) / GRPAN * 100 (if ask available, else use last)
                    ask_price_for_buy = float(ask) if ask > 0 else last_price
                    ask_buy_ucuzluk = ((ask_price_for_buy - grpan_price) / grpan_price) * 100 if ask_price_for_buy > 0 else 0
                    # Ask Sell: (ask - GRPAN) / GRPAN * 100
                    ask_sell_pahalilik = ((float(ask) - grpan_price) / grpan_price) * 100 if ask > 0 else 0
                    # Front Sell: (last - GRPAN) / GRPAN * 100
                    front_sell_pahalilik = ((last_price - grpan_price) / grpan_price) * 100 if last_price > 0 else 0
                    # Bid Sell: (bid - GRPAN) / GRPAN * 100
                    bid_sell_pahalilik = ((float(bid) - grpan_price) / grpan_price) * 100 if bid > 0 else 0
                else:
                    # If GRPAN not available, fallback to RWVAP or zero
                    if rwvap_price and rwvap_price > 0:
                        front_buy_ucuzluk = ((last_price - rwvap_price) / rwvap_price) * 100 if last_price > 0 else 0
                        ask_buy_ucuzluk = ((float(ask) - rwvap_price) / rwvap_price) * 100 if ask > 0 else 0
                        ask_sell_pahalilik = ((float(ask) - rwvap_price) / rwvap_price) * 100 if ask > 0 else 0
                        front_sell_pahalilik = ((last_price - rwvap_price) / rwvap_price) * 100 if last_price > 0 else 0
                        bid_sell_pahalilik = ((float(bid) - rwvap_price) / rwvap_price) * 100 if bid > 0 else 0
                    else:
                        # No GRPAN or RWVAP available - set to zero (will show as 0, not "-")
                        front_buy_ucuzluk = 0
                        ask_buy_ucuzluk = 0
                        ask_sell_pahalilik = 0
                        front_sell_pahalilik = 0
                        bid_sell_pahalilik = 0
            
            # Final scores (matching Janall exactly)
            final_thg_raw = static_row.get('FINAL_THG', 0)
            final_thg = float(final_thg_raw) if final_thg_raw != 'N/A' and final_thg_raw else 0
            
            short_final_raw = static_row.get('SHORT_FINAL', 0)
            short_final = float(short_final_raw) if short_final_raw != 'N/A' and short_final_raw else 0
            
            # Final skor = FINAL_THG - 1000 * ucuzluk/pahalılık_skoru
            # JANALL FORMULA: final_bb = final_thg - 1000 * bid_buy_ucuzluk
            # Note: In RELATIVE mode, scores are in cents. In ABSOLUTE mode, scores are in percentage.
            # To maintain consistency, we convert absolute percentage to "cents equivalent" by dividing by 100
            # (since 1% = 1 cent for a $1 price, but we scale by 100 to match RELATIVE mode behavior)
            if pricing_mode == "RELATIVE":
                # RELATIVE: scores are already in cents, use directly
                # JANALL uses 1000 as multiplier (not 800!)
                final_bb = final_thg - 1000 * bid_buy_ucuzluk
                final_fb = final_thg - 1000 * front_buy_ucuzluk
                final_ab = final_thg - 1000 * ask_buy_ucuzluk
                final_as = final_thg - 1000 * ask_sell_pahalilik
                final_fs = final_thg - 1000 * front_sell_pahalilik
                final_bs = final_thg - 1000 * bid_sell_pahalilik
                
                # Short final scores
                final_sas = short_final - 1000 * ask_sell_pahalilik if short_final > 0 else 0
                final_sfs = short_final - 1000 * front_sell_pahalilik if short_final > 0 else 0
                final_sbs = short_final - 1000 * bid_sell_pahalilik if short_final > 0 else 0
            else:
                # ABSOLUTE: scores are in percentage, convert to "cents equivalent" for consistency
                # Divide by 100 to convert percentage to decimal, then multiply by 100 to get "cents equivalent"
                # Actually, we keep percentage as-is but adjust the multiplier: 1000 * (percentage / 100) = 10 * percentage
                # This maintains the same scale as RELATIVE mode
                final_bb = final_thg - 10 * bid_buy_ucuzluk
                final_fb = final_thg - 10 * front_buy_ucuzluk
                final_ab = final_thg - 10 * ask_buy_ucuzluk
                final_as = final_thg - 10 * ask_sell_pahalilik
                final_fs = final_thg - 10 * front_sell_pahalilik
                final_bs = final_thg - 10 * bid_sell_pahalilik
                
                # Short final scores
                final_sas = short_final - 10 * ask_sell_pahalilik if short_final > 0 else 0
                final_sfs = short_final - 10 * front_sell_pahalilik if short_final > 0 else 0
                final_sbs = short_final - 10 * bid_sell_pahalilik if short_final > 0 else 0
            
            # Round scores (matching Janall: 2 decimals for scores, 4 for spread)
            result = {
                'status': 'OK',
                'pricing_mode': pricing_mode,  # NEW: RELATIVE or ABSOLUTE
                'benchmark_type': benchmark_type,
                'benchmark_chg': round(benchmark_chg, 4) if benchmark_chg is not None else None,
                'Bid_buy_ucuzluk_skoru': round(bid_buy_ucuzluk, 2),
                'Front_buy_ucuzluk_skoru': round(front_buy_ucuzluk, 2),
                'Ask_buy_ucuzluk_skoru': round(ask_buy_ucuzluk, 2),
                'Ask_sell_pahalilik_skoru': round(ask_sell_pahalilik, 2),
                'Front_sell_pahalilik_skoru': round(front_sell_pahalilik, 2),
                'Bid_sell_pahalilik_skoru': round(bid_sell_pahalilik, 2),
                'Final_BB_skor': round(final_bb, 2),
                'Final_FB_skor': round(final_fb, 2),
                'Final_AB_skor': round(final_ab, 2),
                'Final_AS_skor': round(final_as, 2),
                'Final_FS_skor': round(final_fs, 2),
                'Final_BS_skor': round(final_bs, 2),
                'Final_SAS_skor': round(final_sas, 2),
                'Final_SFS_skor': round(final_sfs, 2),
                'Final_SBS_skor': round(final_sbs, 2),
                'Spread': round(spread, 4)
            }
            
            # Add GRPAN/RWVAP info for debugging (absolute mode)
            if pricing_mode == "ABSOLUTE":
                result['grpan_price'] = grpan_price
                result['rwvap_price'] = rwvap_price
            
            return result
            
        except Exception as e:
            logger.error(f"Error computing overlay scores for {symbol}: {e}", exc_info=True)
            return {
                'status': 'ERROR',
                'error': str(e)
            }
    
    def process_dirty_queue(
        self,
        static_store,
        market_data_cache: Dict[str, Dict[str, Any]],
        etf_market_data: Dict[str, Dict[str, Any]],
        etf_prev_close: Dict[str, float]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Process dirty symbols queue with throttle and backpressure.
        
        Args:
            static_store: StaticDataStore instance
            market_data_cache: Market data cache {symbol: {bid, ask, last, prev_close}}
            etf_market_data: ETF market data {ETF: {last, ...}}
            etf_prev_close: ETF previous close {ETF: prev_close}
            
        Returns:
            Dict of computed results {symbol: overlay_scores}
        """
        if not self.dirty_symbols:
            return {}
        
        # Process all dirty symbols (no queue size limit)
        queue_size = len(self.dirty_symbols)
        symbols_to_process = list(self.dirty_symbols)
        
        # Update stats
        self.stats['max_queue_size_seen'] = max(self.stats['max_queue_size_seen'], queue_size)
        
        # Batch processing
        batch_start_time = time.time()
        computed_results = {}
        symbols_processed = 0
        
        for symbol in symbols_to_process:
            # Check throttle (min interval per symbol)
            last_compute = self.last_compute_time.get(symbol, 0)
            elapsed_ms = (time.time() - last_compute) * 1000
            if elapsed_ms < self.min_interval_ms:
                # Skip this symbol, will be processed in next cycle
                continue
            
            # No batch size limit - process all symbols in queue
            # (batch_size is set to 999999 to effectively disable limit)
            
            # Get static data
            static_row = static_store.get_static_data(symbol)
            if not static_row:
                self.dirty_symbols.discard(symbol)
                continue
            
            # Get live quote
            live_quote = market_data_cache.get(symbol, {})
            if not live_quote:
                # No market data yet, keep in queue
                continue
            
            # Check if quote changed (additional validation)
            current_quote = {
                'bid': live_quote.get('bid'),
                'ask': live_quote.get('ask'),
                'last': live_quote.get('last')
            }
            last_quote = self.last_quote.get(symbol, {})
            
            # If quote hasn't changed and benchmark hasn't changed, skip
            if (current_quote == last_quote and 
                symbol in self.last_benchmark_chg and
                self.last_benchmark_chg[symbol] == live_quote.get('benchmark_chg')):
                # Quote and benchmark unchanged, remove from dirty queue
                self.dirty_symbols.discard(symbol)
                continue
            
            # Compute overlay scores
            try:
                result = self.compute_overlay_scores(
                    symbol=symbol,
                    static_row=static_row,
                    live_quote=live_quote,
                    benchmarks_live=etf_market_data,
                    benchmarks_prev_close=etf_prev_close
                )
                
                # Update cache
                self.overlay_cache[symbol] = result
                
                # Update tracking
                self.last_compute_time[symbol] = time.time()
                self.last_quote[symbol] = current_quote.copy()
                if result.get('benchmark_chg') is not None:
                    self.last_benchmark_chg[symbol] = result['benchmark_chg']
                
                # Remove from dirty queue
                self.dirty_symbols.discard(symbol)
                
                computed_results[symbol] = result
                symbols_processed += 1
                
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}", exc_info=True)
                # Remove from queue to prevent infinite retry
                self.dirty_symbols.discard(symbol)
        
        # Update stats
        batch_duration_ms = (time.time() - batch_start_time) * 1000
        self.stats['total_computes'] += symbols_processed
        self.stats['total_time_ms'] += batch_duration_ms
        self.stats['batch_count'] += 1
        
        if symbols_processed > 0:
            avg_time_ms = batch_duration_ms / symbols_processed
            logger.debug(
                f"Processed {symbols_processed} symbols in {batch_duration_ms:.1f}ms "
                f"(avg {avg_time_ms:.1f}ms/symbol, queue size: {len(self.dirty_symbols)})"
            )
        
        return computed_results
    
    def get_overlay_scores(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get cached overlay scores for a symbol.
        
        Args:
            symbol: Symbol to get scores for
            
        Returns:
            Overlay scores dict or None if not computed yet
        """
        return self.overlay_cache.get(symbol)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        avg_time_ms = 0.0
        if self.stats['total_computes'] > 0:
            avg_time_ms = self.stats['total_time_ms'] / self.stats['total_computes']
        
        return {
            'total_computes': self.stats['total_computes'],
            'total_time_ms': self.stats['total_time_ms'],
            'avg_time_ms': avg_time_ms,
            'batch_count': self.stats['batch_count'],
            'max_queue_size_seen': self.stats['max_queue_size_seen'],
            'current_queue_size': len(self.dirty_symbols)
        }


# Global instance
_pricing_overlay_engine: Optional[PricingOverlayEngine] = None


def get_pricing_overlay_engine() -> Optional[PricingOverlayEngine]:
    """Get global PricingOverlayEngine instance"""
    global _pricing_overlay_engine
    if _pricing_overlay_engine is None:
        # Try to get from market_data_routes
        try:
            from app.api.market_data_routes import pricing_overlay_engine as routes_engine
            if routes_engine:
                _pricing_overlay_engine = routes_engine
        except Exception:
            pass
    return _pricing_overlay_engine


def initialize_pricing_overlay_engine(config: Optional[Dict[str, Any]] = None) -> PricingOverlayEngine:
    """Initialize global PricingOverlayEngine instance"""
    global _pricing_overlay_engine
    # If already initialized in market_data_routes, use that instance
    try:
        from app.api.market_data_routes import pricing_overlay_engine as routes_engine
        if routes_engine:
            _pricing_overlay_engine = routes_engine
            logger.info("PricingOverlayEngine global instance synced from market_data_routes")
            return _pricing_overlay_engine
    except Exception:
        pass
    # Otherwise create new instance
    _pricing_overlay_engine = PricingOverlayEngine(config=config)
    logger.info("PricingOverlayEngine global instance initialized")
    return _pricing_overlay_engine

