"""app/market_data/grpan_tick_fetcher.py

Bootstrap/Recovery modunda Hammer Pro'dan getTicks komutu ile son tick'leri çekip
GRPAN engine'e gönderen servis.

Bootstrap/Recovery modu:
- Sürekli polling YAPMAZ
- Sadece şu durumlarda getTicks çağırır:
  - Backend startup (ilk bootstrap)
  - Symbol ilk kez eklendiğinde
  - GRPAN state boşsa
  - Uzun süre trade gelmemişse (örn 5-10 dk)

Asıl veri kaynağı: Real-time Hammer trade print event'leri (event-driven)
"""

import threading
import time
from typing import Dict, Any, Optional, List
from collections import deque

from app.core.logger import logger
from app.live.symbol_mapper import SymbolMapper


class GRPANTickFetcher:
    """
    Periyodik olarak getTicks komutu ile son tick'leri çekip GRPAN engine'e gönderen servis.
    
    Janall uygulamasındaki implementasyona benzer şekilde çalışır:
    - Her sembol için periyodik olarak getTicks çağırır
    - Son 50 tick alır (9 lot altı filtrelenir, son 15 kullanılır)
    - TradePrintRouter üzerinden GRPAN engine'e gönderir
    """
    
    def __init__(
        self,
        hammer_client,
        trade_print_router,
        grpan_engine=None,
        last_few_ticks: int = 150,  # Changed to 150 for extended buffer
        min_lot_size: int = 10,
        stale_threshold_sec: float = 600.0,  # 10 minutes
        polling_mode: bool = False,
        polling_interval: float = 60.0
    ):
        """
        Initialize GRPAN tick fetcher.
        
        Args:
            hammer_client: HammerClient instance
            trade_print_router: TradePrintRouter instance
            grpan_engine: GRPANEngine instance (for state checking)
            last_few_ticks: Number of last ticks to fetch for BOOTSTRAP (default: 150)
            min_lot_size: Minimum lot size to include (default: 10)
            stale_threshold_sec: Time threshold for stale state check (default: 600s = 10 min)
            polling_mode: If True, continuously poll history every interval (default: False)
            polling_interval: Interval for polling in seconds (default: 60s)
        """
        self.hammer_client = hammer_client
        self.trade_print_router = trade_print_router
        self.grpan_engine = grpan_engine
        self.last_few_ticks = last_few_ticks
        self.min_lot_size = min_lot_size
        self.stale_threshold_sec = stale_threshold_sec
        self.polling_mode = polling_mode
        self.polling_interval = polling_interval
        
        # Threading
        self._fetch_thread: Optional[threading.Thread] = None
        self._running = False
        
        # Track symbols and their state
        self.symbols_to_fetch: List[str] = []
        self._symbols_lock = threading.Lock()
        
        # Track last trade time per symbol: {symbol: last_trade_timestamp}
        self.last_trade_time: Dict[str, float] = {}
        
        # Track if symbol has been bootstrapped: {symbol: bool}
        self.bootstrapped_symbols: Set[str] = set()
        
        # Metrics
        self.metrics = {
            'total_fetches': 0,
            'successful_fetches': 0,
            'failed_fetches': 0,
            'bootstrap_fetches': 0,
            'recovery_fetches': 0,
            'polling_fetches': 0,
            'total_ticks_processed': 0,
            'last_fetch_time': None
        }
    
    def add_symbols(self, symbols: List[str], bootstrap: bool = True):
        """
        Add symbols to fetch list.
        Args:
            symbols: List of symbols (in display format, e.g., "CIM PRB")
            bootstrap: If True, immediately bootstrap these symbols
        """
        with self._symbols_lock:
            for symbol in symbols:
                if symbol not in self.symbols_to_fetch:
                    self.symbols_to_fetch.append(symbol)
                    self.last_trade_time[symbol] = time.time()  # Initialize
            
            if bootstrap:
                # Bootstrap new symbols immediately
                for symbol in symbols:
                    if symbol not in self.bootstrapped_symbols:
                        self._bootstrap_symbol(symbol)
            
            logger.info(f"📊 GRPAN tick fetcher: {len(symbols)} symbols added, total: {len(self.symbols_to_fetch)}")

    def _bootstrap_symbol(self, symbol: str):
        """Bootstrap a symbol (fetch initial ticks)"""
        try:
            logger.info(f"🔄 GRPAN bootstrap: Fetching initial ticks for {symbol}")
            self._fetch_ticks_for_symbol(symbol, is_bootstrap=True)
            self.bootstrapped_symbols.add(symbol)
            self.metrics['bootstrap_fetches'] += 1
        except Exception as e:
            logger.error(f"Error bootstrapping {symbol}: {e}", exc_info=True)

    def _should_fetch_for_symbol(self, symbol: str) -> bool:
        """
        Check if we should fetch ticks for a symbol (bootstrap/recovery logic).
        Returns:
            True if should fetch, False otherwise
        """
        # Check if symbol has GRPAN state
        if self.grpan_engine:
            # Check if any window has data
            all_windows = self.grpan_engine.get_all_windows_for_symbol(symbol)
            has_data = any(
                w.get('grpan_price') is not None 
                for w in all_windows.values()
            )
            
            if not has_data:
                # No GRPAN data - need bootstrap
                return True
        
        # Check if symbol has been bootstrapped
        if symbol not in self.bootstrapped_symbols:
            # Not bootstrapped yet
            return True
        
        # Check if state is stale (no trades for a while)
        last_trade = self.last_trade_time.get(symbol, 0)
        current_time = time.time()
        time_since_last_trade = current_time - last_trade
        
        if time_since_last_trade > self.stale_threshold_sec:
            # State is stale - need recovery
            logger.debug(f"GRPAN recovery: {symbol} state is stale ({time_since_last_trade:.0f}s since last trade)")
            return True
        
        # No need to fetch
        return False

    def remove_symbols(self, symbols: List[str]):
        """
        Remove symbols from fetch list.
        Args:
            symbols: List of symbols to remove
        """
        with self._symbols_lock:
            for symbol in symbols:
                if symbol in self.symbols_to_fetch:
                    self.symbols_to_fetch.remove(symbol)
            logger.info(f"📊 GRPAN tick fetcher: {len(symbols)} symbols removed, remaining: {len(self.symbols_to_fetch)}")

    def start(self):
        """Start the tick fetcher thread."""
        if self._running:
            logger.warning("GRPAN tick fetcher already running")
            return
        
        if not self.hammer_client or not self.hammer_client.is_connected():
            logger.error("Hammer client not connected, cannot start GRPAN tick fetcher")
            return
        
        self._running = True
        self._fetch_thread = threading.Thread(target=self._fetch_loop, daemon=True)
        self._fetch_thread.start()
        logger.info(f"🚀 GRPAN tick fetcher started (bootstrap/recovery mode, lastFew: {self.last_few_ticks}, stale_threshold: {self.stale_threshold_sec}s, polling: {self.polling_mode})")

    def stop(self):
        """Stop the tick fetcher thread."""
        self._running = False
        if self._fetch_thread:
            self._fetch_thread.join(timeout=5.0)
        logger.info("🛑 GRPAN tick fetcher stopped")
    
    def _fetch_loop(self):
        """
        Main fetch loop (runs in separate thread).
        Supports both Bootstrap/Recovery (lazy) and Polling (active) modes.
        """
        # Default check interval
        check_interval_sec = self.polling_interval if self.polling_mode else 60.0
        
        while self._running:
            try:
                # Get current symbols to check
                with self._symbols_lock:
                    symbols = self.symbols_to_fetch.copy()
                
                if not symbols:
                    # No symbols to check, wait and retry
                    time.sleep(5)
                    continue
                
                fetched_count = 0
                
                # In polling mode, we iterate all symbols in this cycle
                # If list is huge, we might need to pace it. 
                # Assuming < 500 symbols, it's manageable if Hammer allows.
                
                for symbol in symbols:
                    if not self._running:
                        break
                    
                    try:
                        should_fetch = False
                        is_bootstrap = False
                        use_limit = None
                        
                        if self.polling_mode:
                            # 1. Active Polling Strategy
                            should_fetch = True
                            is_bootstrap = symbol not in self.bootstrapped_symbols
                            # If polling, we don't need 2500 ticks every time, just enough to cover the gap
                            # 500 is safe buffer for 1 minute on prefs
                            # Unless it's bootstrap, then use full history
                            use_limit = self.last_few_ticks if is_bootstrap else 500
                        else:
                            # 2. Lazy Recovery Strategy (Legacy)
                            should_fetch = self._should_fetch_for_symbol(symbol)
                            if should_fetch:
                                is_bootstrap = (symbol not in self.bootstrapped_symbols)
                        
                        if should_fetch:
                            is_recovery = symbol in self.bootstrapped_symbols
                            
                            self._fetch_ticks_for_symbol(symbol, is_bootstrap=not is_recovery, limit_override=use_limit)
                            
                            if self.polling_mode and is_recovery:
                                self.metrics['polling_fetches'] += 1
                            elif is_recovery:
                                self.metrics['recovery_fetches'] += 1
                                
                            fetched_count += 1
                            
                            # Update last trade time
                            self.last_trade_time[symbol] = time.time()
                            
                    except Exception as e:
                        logger.error(f"Error checking/fetching ticks for {symbol}: {e}", exc_info=True)
                        self.metrics['failed_fetches'] += 1
                    
                    # Small delay between symbols to avoid Hammer rate limits
                    time.sleep(0.05) 
                
                if fetched_count > 0:
                    logger.debug(f"GRPAN tick fetcher: Fetched {fetched_count} symbols (Polling: {self.polling_mode})")
                    self.metrics['last_fetch_time'] = time.time()
                
                # Wait before next cycle
                time.sleep(check_interval_sec)
                
            except Exception as e:
                logger.error(f"Error in GRPAN tick fetcher loop: {e}", exc_info=True)
                time.sleep(check_interval_sec)

    def _fetch_ticks_for_symbol(self, symbol: str, is_bootstrap: bool = False, limit_override: int = None):
        """
        Fetch ticks for a single symbol and send to GRPAN engine.
        
        Args:
            symbol: Symbol in display format (e.g., "CIM PRB")
            limit_override: Optional override for number of ticks to fetch
        """
        try:
            # Determine limit
            limit_to_use = limit_override if limit_override else self.last_few_ticks
            
            # Retry logic with aggressive fallback
            tick_data = None
            amounts_to_try = [limit_to_use]
            
            # Always add fallbacks, even for small requests
            if limit_to_use > 1000:
                amounts_to_try.extend([1500, 500, 100, 10])
            elif limit_to_use > 500:
                amounts_to_try.extend([300, 100, 10])
            elif limit_to_use > 100:
                amounts_to_try.extend([50, 10])
            elif limit_to_use > 10:
                amounts_to_try.append(10)
            
            # Additional safety for extreme illiquidity
            if 1 not in amounts_to_try and 5 not in amounts_to_try:
                amounts_to_try.append(5)

            # Deduplicate and sort descending
            amounts_to_try = sorted(list(set(amounts_to_try)), reverse=True)
            
            for count in amounts_to_try:
                try:
                    # Use slightly longer timeout for larger requests if possible, but HammerClient defaults to 10s
                    # We rely on the fallback amounts to solve the timeout, not extending the timer indefinitely.
                    tick_data = self.hammer_client.get_ticks(
                        symbol,
                        lastFew=count,
                        tradesOnly=True,  # CRITICAL: Only want trades
                        regHoursOnly=False # CRITICAL: Get ALL hours (avoid missing trades due to session flags)
                    )
                    
                    if tick_data and 'data' in tick_data:
                        if count < limit_to_use:
                            logger.info(f"⚠️ GRPAN fetch {symbol}: Succeeded with fallback limit {count} (requested {limit_to_use})")
                        break # Success
                except Exception as e:
                     logger.warning(f"⚠️ GRPAN fetch {symbol}: Error fetching {count} ticks: {e}")
 
            
            # ... rest of logic ...
            if not tick_data or 'data' not in tick_data:
                 # Be less spammy in polling mode logs unless robust failure
                 if not self.polling_mode:
                    logger.error(f"❌ GRPAN tick fetcher: All fetch attempts failed for {symbol}")
                 return

            all_ticks = tick_data.get('data', [])
            if not all_ticks:
                return
            
            # Filter Logic (Strict)
            # 1. FNRA/ADFN/TRF: ONLY accept sizes of exactly 100 or 200.
            # 2. Others (NSDQ/ARCA/etc): Accept size >= 15.
            
            filtered_ticks = []
            for tick in all_ticks:
                size = tick.get('s', 0)
                venue = tick.get('e', 'UNKNOWN').upper()
                
                # Check for "Dark Pool" venues
                # Hammer venue codes: 'D' often ADFN, 'Q' NASDAQ, 'P' ARCA etc.
                # However, tick['e'] usually returns mapped string like 'ADFN' or just char.
                # User report: "FNRA", "ADFN". 
                # Strategy: If venue contains FNRA, ADFN, TRF, or is 'D' (common finra code)
                
                is_dark = False
                if 'FNRA' in venue or 'ADFN' in venue or 'TRF' in venue:
                    is_dark = True
                elif venue == 'D': # Common code for FINRA/ADFN
                    is_dark = True
                
                if is_dark:
                    # STRICT Rule: Only 100 or 200
                    if size == 100 or size == 200:
                        filtered_ticks.append(tick)
                else:
                    # Standard Rule: size >= 15
                    if size >= 15:
                        filtered_ticks.append(tick)
            
            # In polling mode, we send whatever we got filtered, assuming duplication check handles the overlap
            ticks_to_send = filtered_ticks
            
            if not ticks_to_send and not self.polling_mode:
                 # Debug log only if not polling (polling naturally has empty windows)
                 logger.debug(f"GRPAN tick fetcher {symbol}: Insufficient ticks")
                 return
            
            if ticks_to_send:
                # logger.info(f"📊 Sending {len(ticks_to_send)} ticks for {symbol}")
                # Send each tick to TradePrintRouter
                ticks_sent = 0
                for tick in ticks_to_send:
                    try:
                        trade_print_data = {
                            'time': tick.get('t'),
                            'price': float(tick.get('p', 0)),
                            'size': float(tick.get('s', 0)),
                            'venue': tick.get('e', 'UNKNOWN')
                        }
                        if self.trade_print_router:
                            self.trade_print_router.route_trade_print(trade_print_data, symbol)
                            ticks_sent += 1
                    except Exception:
                        continue
                
                if ticks_sent > 0:
                     if is_bootstrap:
                         # Log critical bootstrap info
                         logger.info(f"📊 GRPAN tick fetcher ({'bootstrap' if is_bootstrap else 'update'}): {symbol} - {ticks_sent} ticks sent")
                     elif self.polling_mode and ticks_sent > 5:
                         # Only log substantial updates in polling mode to avoid spam
                         logger.debug(f"📊 GRPAN polling: {symbol} - {ticks_sent} ticks")

                self.metrics['successful_fetches'] += 1
                self.metrics['total_ticks_processed'] += ticks_sent
            
            # Mark as bootstrapped
            if is_bootstrap:
                self.bootstrapped_symbols.add(symbol)
            
        except Exception as e:
            logger.error(f"Error fetching ticks for {symbol}: {e}", exc_info=True)
            self.metrics['failed_fetches'] += 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get fetcher metrics."""
        return self.metrics.copy()

