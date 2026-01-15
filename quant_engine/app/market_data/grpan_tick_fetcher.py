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
        stale_threshold_sec: float = 600.0  # 10 minutes
    ):
        """
        Initialize GRPAN tick fetcher (Bootstrap/Recovery mode).
        
        Args:
            hammer_client: HammerClient instance
            trade_print_router: TradePrintRouter instance
            grpan_engine: GRPANEngine instance (for state checking)
            last_few_ticks: Number of last ticks to fetch (default: 50)
            min_lot_size: Minimum lot size to include (default: 10)
            stale_threshold_sec: Time threshold for stale state check (default: 600s = 10 min)
        """
        self.hammer_client = hammer_client
        self.trade_print_router = trade_print_router
        self.grpan_engine = grpan_engine
        self.last_few_ticks = last_few_ticks
        self.min_lot_size = min_lot_size
        self.stale_threshold_sec = stale_threshold_sec
        
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
        logger.info(f"🚀 GRPAN tick fetcher started (bootstrap/recovery mode, lastFew: {self.last_few_ticks}, stale_threshold: {self.stale_threshold_sec}s)")
    
    def stop(self):
        """Stop the tick fetcher thread."""
        self._running = False
        if self._fetch_thread:
            self._fetch_thread.join(timeout=5.0)
        logger.info("🛑 GRPAN tick fetcher stopped")
    
    def _fetch_loop(self):
        """
        Main fetch loop (runs in separate thread) - Bootstrap/Recovery mode.
        
        Only fetches when needed (bootstrap/recovery), not continuously.
        """
        # Check interval for stale state (every 60 seconds)
        check_interval_sec = 60.0
        
        while self._running:
            try:
                # Get current symbols to check
                with self._symbols_lock:
                    symbols = self.symbols_to_fetch.copy()
                
                if not symbols:
                    # No symbols to check, wait and retry
                    time.sleep(check_interval_sec)
                    continue
                
                # Check each symbol and fetch only if needed
                fetched_count = 0
                for symbol in symbols:
                    if not self._running:
                        break
                    
                    try:
                        if self._should_fetch_for_symbol(symbol):
                            is_recovery = symbol in self.bootstrapped_symbols
                            self._fetch_ticks_for_symbol(symbol, is_bootstrap=not is_recovery)
                            if is_recovery:
                                self.metrics['recovery_fetches'] += 1
                            fetched_count += 1
                            
                            # Update last trade time
                            self.last_trade_time[symbol] = time.time()
                    except Exception as e:
                        logger.error(f"Error checking/fetching ticks for {symbol}: {e}", exc_info=True)
                        self.metrics['failed_fetches'] += 1
                    
                    # Small delay between symbols
                    time.sleep(0.1)
                
                if fetched_count > 0:
                    logger.debug(f"GRPAN tick fetcher: Fetched {fetched_count} symbols (bootstrap/recovery)")
                    self.metrics['last_fetch_time'] = time.time()
                
                # Wait before next check
                time.sleep(check_interval_sec)
                
            except Exception as e:
                logger.error(f"Error in GRPAN tick fetcher loop: {e}", exc_info=True)
                time.sleep(check_interval_sec)
    
    def _fetch_ticks_for_symbol(self, symbol: str, is_bootstrap: bool = False):
        """
        Fetch ticks for a single symbol and send to GRPAN engine.
        
        Args:
            symbol: Symbol in display format (e.g., "CIM PRB")
        """
        try:
            # Get ticks from Hammer Pro (like janall: lastFew=50, tradesOnly=False, regHoursOnly=True)
            tick_data = self.hammer_client.get_ticks(
                symbol,
                lastFew=self.last_few_ticks,
                tradesOnly=False,  # tradesOnly=False (venue bilgisi için, janall gibi)
                regHoursOnly=True
            )
            
            if not tick_data or 'data' not in tick_data:
                logger.debug(f"GRPAN tick fetcher: No tick data for {symbol}")
                return
            
            all_ticks = tick_data.get('data', [])
            if not all_ticks:
                logger.debug(f"GRPAN tick fetcher: Empty tick data for {symbol}")
                return
            
            # Filter: size > 9 (like janall: 9 lot ve altındaki print'leri IGNORE et)
            filtered_ticks = [
                tick for tick in all_ticks 
                if tick.get('s', 0) > 9  # 's' = size field in Hammer Pro response
            ]
            
            ignored_count = len(all_ticks) - len(filtered_ticks)
            if ignored_count > 0:
                logger.debug(f"GRPAN tick fetcher {symbol}: {ignored_count} ticks ignored (≤9 lot)")
            
            # Get last 150 ticks (for extended buffer) - but keep last 15 for latest_pan too
            # We'll send all filtered ticks (up to 150) to populate extended_prints_store
            ticks_to_send = filtered_ticks[-self.last_few_ticks:] if len(filtered_ticks) >= self.last_few_ticks else filtered_ticks
            
            if len(ticks_to_send) < 3:
                logger.debug(f"GRPAN tick fetcher {symbol}: Insufficient ticks ({len(ticks_to_send)} ticks, 10+ lot)")
                return
            
            logger.info(f"📊 GRPAN bootstrap {symbol}: Sending {len(ticks_to_send)} ticks to GRPAN engine (extended buffer)")
            
            # Send each tick to TradePrintRouter (all ticks go to extended_prints_store)
            ticks_sent = 0
            for tick in ticks_to_send:
                try:
                    # Normalize tick to TradePrintRouter format
                    # Hammer Pro tick format: {'t': timestamp, 'p': price, 's': size, 'b': bid, 'a': ask}
                    trade_print_data = {
                        'time': tick.get('t'),  # ISO 8601 timestamp
                        'price': float(tick.get('p', 0)),
                        'size': float(tick.get('s', 0)),
                        'venue': tick.get('e', 'UNKNOWN')  # 'e' = exchange/venue field
                    }
                    
                    # Route to GRPAN engine via TradePrintRouter
                    if self.trade_print_router:
                        self.trade_print_router.route_trade_print(trade_print_data, symbol)
                        ticks_sent += 1
                        
                except Exception as e:
                    logger.debug(f"Error processing tick for {symbol}: {e}")
                    continue
            
            if ticks_sent > 0:
                mode_str = "bootstrap" if is_bootstrap else "recovery"
                logger.info(
                    f"📊 GRPAN tick fetcher ({mode_str}): {symbol} - {ticks_sent} ticks sent to GRPAN engine "
                    f"(from {len(all_ticks)} total, {len(filtered_ticks)} filtered, {len(ticks_to_send)} used)"
                )
                self.metrics['successful_fetches'] += 1
                self.metrics['total_ticks_processed'] += ticks_sent
            else:
                logger.debug(f"GRPAN tick fetcher: {symbol} - No ticks sent (all filtered or invalid)")
            
            self.metrics['total_fetches'] += 1
            
            # Mark as bootstrapped if this was a bootstrap
            if is_bootstrap:
                self.bootstrapped_symbols.add(symbol)
            
        except Exception as e:
            logger.error(f"Error fetching ticks for {symbol}: {e}", exc_info=True)
            self.metrics['failed_fetches'] += 1
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get fetcher metrics."""
        return self.metrics.copy()

