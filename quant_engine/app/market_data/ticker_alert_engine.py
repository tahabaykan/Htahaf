"""app/market_data/ticker_alert_engine.py

Ticker Alert Engine - Lightspeed-style ticker alert functionality.
Tracks daily high/low from Hammer snapshot and emits NEW_HIGH/NEW_LOW events when broken.

Design:
- Daily high/low loaded from Hammer getSymbolSnapshot at startup (ONCE)
- Panel starts EMPTY (no alerts shown)
- Only emits alerts when last_price breaks daily high/low
- Session-based: tab opens → snapshot baseline, reset → current last_price becomes baseline
"""

from typing import Dict, Optional, List
from datetime import datetime
from collections import defaultdict
import time

from app.core.logger import logger


class TickerAlert:
    """Represents a ticker alert event"""
    
    def __init__(
        self,
        symbol: str,
        event_type: str,  # "NEW_HIGH" or "NEW_LOW"
        price: float,
        daily_high: Optional[float],
        daily_low: Optional[float],
        timestamp: str,
        change: Optional[float] = None,
        change_percent: Optional[float] = None
    ):
        self.symbol = symbol
        self.event_type = event_type
        self.price = price
        self.daily_high = daily_high
        self.daily_low = daily_low
        self.timestamp = timestamp
        self.change = change
        self.change_percent = change_percent
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "symbol": self.symbol,
            "event_type": self.event_type,
            "price": self.price,
            "daily_high": self.daily_high,
            "daily_low": self.daily_low,
            "timestamp": self.timestamp,
            "change": self.change,
            "change_percent": self.change_percent
        }


class TickerAlertEngine:
    """
    Lightspeed-style ticker alert engine.
    
    Features:
    - Daily high/low from Hammer getSymbolSnapshot (startup, ONCE)
    - Panel starts empty
    - Only emits alerts when daily high/low is broken
    - Session-based tracking (tab opens → snapshot baseline, reset → current price baseline)
    """
    
    def __init__(self):
        # DAILY HIGH/LOW CACHE (from Hammer snapshot, NOT shown in UI)
        # Global daily high/low (loaded from snapshot at startup)
        self._daily_high_cache: Dict[str, float] = {}  # symbol -> daily high
        self._daily_low_cache: Dict[str, float] = {}   # symbol -> daily low
        
        # Tab-based daily high/low (session_id -> {symbol -> {high, low}})
        self._tab_daily_cache: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(dict)
        
        # Track which symbols have snapshot loaded (to prevent re-initialization)
        self._snapshot_loaded: Dict[str, bool] = {}  # symbol -> True if snapshot loaded
        
        # Alert history (ONLY events, not baseline data)
        self._alert_history: List[TickerAlert] = []
        self._max_history = 1000  # Keep last 1000 alerts
        
        # Track which symbols have already emitted alerts (to prevent duplicates)
        self._emitted_alerts: Dict[str, Dict[str, float]] = {}  # symbol -> {NEW_HIGH: price, NEW_LOW: price}
        
        logger.info("TickerAlertEngine initialized (Lightspeed-style with daily high/low cache)")
    
    def load_daily_high_low_from_snapshot(
        self,
        symbol: str,
        daily_high: float,
        daily_low: float,
        session_id: Optional[str] = None
    ):
        """
        Load daily high/low from Hammer snapshot (startup or tab open).
        
        Args:
            symbol: Symbol name
            daily_high: Daily high from snapshot.high
            daily_low: Daily low from snapshot.low
            session_id: Optional session ID for tab-based cache
        """
        if daily_high <= 0 or daily_low <= 0:
            return
        
        if session_id:
            # Tab-based cache
            if symbol not in self._tab_daily_cache[session_id]:
                self._tab_daily_cache[session_id][symbol] = {}
            self._tab_daily_cache[session_id][symbol]['high'] = daily_high
            self._tab_daily_cache[session_id][symbol]['low'] = daily_low
            logger.debug(f"📊 Tab daily cache loaded for {symbol}: high={daily_high}, low={daily_low} (session={session_id})")
        else:
            # Global cache
            self._daily_high_cache[symbol] = daily_high
            self._daily_low_cache[symbol] = daily_low
            self._snapshot_loaded[symbol] = True
            logger.debug(f"📊 Global daily cache loaded for {symbol}: high={daily_high}, low={daily_low}")
    
    def process_price_update(
        self,
        symbol: str,
        last_price: float,
        prev_close: Optional[float] = None,
        timestamp: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> Optional[TickerAlert]:
        """
        Process a price update and check if daily high/low is broken.
        
        CRITICAL: Only uses last_price, NOT bid/ask.
        
        Args:
            symbol: Symbol name
            last_price: Last trade price (from L1Update, NOT bid/ask)
            prev_close: Previous close price (for change calculation)
            timestamp: Event timestamp (ISO format)
            session_id: Optional session ID for tab-based tracking
        
        Returns:
            TickerAlert if daily high/low broken, None otherwise
        """
        if last_price <= 0:
            return None
        
        if timestamp is None:
            timestamp = datetime.now().isoformat()
        
        # Get daily high/low for this symbol (tab-based or global)
        if session_id and session_id in self._tab_daily_cache:
            daily_high = self._tab_daily_cache[session_id].get(symbol, {}).get('high', 0.0)
            daily_low = self._tab_daily_cache[session_id].get(symbol, {}).get('low', float('inf'))
        else:
            daily_high = self._daily_high_cache.get(symbol, 0.0)
            daily_low = self._daily_low_cache.get(symbol, float('inf'))
        
        # If no daily high/low loaded yet, skip (will be loaded from snapshot)
        if daily_high == 0.0 and daily_low == float('inf'):
            # Not loaded yet - skip (snapshot will load it)
            return None
        
        alert = None
        
        # Check for NEW_DAILY_HIGH (last_price > daily_high)
        if last_price > daily_high:
            # Check if we already emitted this alert (prevent duplicates)
            emitted_high = self._emitted_alerts.get(symbol, {}).get('NEW_HIGH', 0.0)
            if last_price > emitted_high:
                # Calculate change
                change = prev_close and prev_close > 0 and (last_price - prev_close) or None
                change_percent = change and prev_close and (change / prev_close * 100) or None
                
                alert = TickerAlert(
                    symbol=symbol,
                    event_type="NEW_HIGH",
                    price=last_price,
                    daily_high=daily_high,
                    daily_low=daily_low,
                    timestamp=timestamp,
                    change=change,
                    change_percent=change_percent
                )
                
                # Update emitted alerts
                if symbol not in self._emitted_alerts:
                    self._emitted_alerts[symbol] = {}
                self._emitted_alerts[symbol]['NEW_HIGH'] = last_price
                
                # Update daily high cache (new high becomes new daily high)
                if session_id:
                    self._tab_daily_cache[session_id][symbol]['high'] = last_price
                else:
                    self._daily_high_cache[symbol] = last_price
        
        # Check for NEW_DAILY_LOW (last_price < daily_low)
        elif last_price < daily_low:
            # Check if we already emitted this alert (prevent duplicates)
            emitted_low = self._emitted_alerts.get(symbol, {}).get('NEW_LOW', float('inf'))
            if last_price < emitted_low:
                # Calculate change
                change = prev_close and prev_close > 0 and (last_price - prev_close) or None
                change_percent = change and prev_close and (change / prev_close * 100) or None
                
                # If we already emitted NEW_HIGH, don't emit NEW_LOW in same update
                if alert is None:
                    alert = TickerAlert(
                        symbol=symbol,
                        event_type="NEW_LOW",
                        price=last_price,
                        daily_high=daily_high,
                        daily_low=daily_low,
                        timestamp=timestamp,
                        change=change,
                        change_percent=change_percent
                    )
                    
                    # Update emitted alerts
                    if symbol not in self._emitted_alerts:
                        self._emitted_alerts[symbol] = {}
                    self._emitted_alerts[symbol]['NEW_LOW'] = last_price
                    
                    # Update daily low cache (new low becomes new daily low)
                    if session_id:
                        self._tab_daily_cache[session_id][symbol]['low'] = last_price
                    else:
                        self._daily_low_cache[symbol] = last_price
        
        # Add to history if alert was generated
        if alert:
            self._alert_history.append(alert)
            # Keep only last N alerts
            if len(self._alert_history) > self._max_history:
                self._alert_history = self._alert_history[-self._max_history:]
        
        return alert
    
    def get_recent_alerts(
        self,
        limit: int = 100,
        event_type: Optional[str] = None,
        symbol: Optional[str] = None
    ) -> List[TickerAlert]:
        """
        Get recent alert events (ONLY events, not baseline data).
        
        Args:
            limit: Maximum number of alerts to return
            event_type: Filter by event type ("NEW_HIGH" or "NEW_LOW")
            symbol: Filter by symbol
        
        Returns:
            List of TickerAlert objects (most recent first)
        """
        alerts = self._alert_history[-limit:] if limit else self._alert_history
        
        # Filter by event_type
        if event_type:
            alerts = [a for a in alerts if a.event_type == event_type]
        
        # Filter by symbol
        if symbol:
            alerts = [a for a in alerts if a.symbol == symbol]
        
        # Return most recent first
        return list(reversed(alerts))
    
    def reset_session(self, session_id: Optional[str] = None, use_current_price: bool = True):
        """
        Reset session daily high/low.
        
        Args:
            session_id: Optional session ID to reset (None = reset global session)
            use_current_price: If True, use current last_price as new daily high/low (session reset)
                              If False, clear cache (will reload from snapshot on next price update)
        """
        if session_id:
            if session_id in self._tab_daily_cache:
                if use_current_price:
                    # Session reset: would need current prices (not available here)
                    # For now, just clear and let it reinitialize from snapshot
                    logger.info(f"Reset tab session daily cache: {session_id} (will reinitialize from snapshot)")
                del self._tab_daily_cache[session_id]
                logger.info(f"Reset tab session: {session_id}")
        else:
            if use_current_price:
                # Global reset: would need current prices
                logger.info("Reset global ticker alert daily cache (will reinitialize from snapshot)")
            self._daily_high_cache.clear()
            self._daily_low_cache.clear()
            self._emitted_alerts.clear()
            self._snapshot_loaded.clear()
            logger.info("Reset global ticker alert session")
    
    def create_tab_session(self, session_id: str) -> str:
        """
        Create a new tab-based session (daily cache will be loaded from snapshot).
        
        Args:
            session_id: Unique session ID (typically timestamp or UUID)
        
        Returns:
            session_id
        """
        self._tab_daily_cache[session_id] = {}
        logger.debug(f"Created tab session: {session_id}")
        return session_id
    
    def get_daily_cache(self, symbol: str, session_id: Optional[str] = None) -> Dict[str, float]:
        """
        Get daily high/low cache for a symbol (for debugging, not shown in UI).
        
        Args:
            symbol: Symbol name
            session_id: Optional session ID
        
        Returns:
            Dict with 'high' and 'low' keys
        """
        if session_id and session_id in self._tab_daily_cache:
            cache = self._tab_daily_cache[session_id].get(symbol, {})
            return {
                'high': cache.get('high', 0.0),
                'low': cache.get('low', float('inf'))
            }
        else:
            return {
                'high': self._daily_high_cache.get(symbol, 0.0),
                'low': self._daily_low_cache.get(symbol, float('inf'))
            }
    
    def is_snapshot_loaded(self, symbol: str) -> bool:
        """Check if snapshot has been loaded for this symbol"""
        return self._snapshot_loaded.get(symbol, False)


# Global singleton instance
_ticker_alert_engine: Optional[TickerAlertEngine] = None


def get_ticker_alert_engine() -> TickerAlertEngine:
    """Get global TickerAlertEngine instance"""
    global _ticker_alert_engine
    if _ticker_alert_engine is None:
        _ticker_alert_engine = TickerAlertEngine()
    return _ticker_alert_engine


def initialize_ticker_alert_engine():
    """
    Initialize global TickerAlertEngine instance.
    
    NOTE: Daily high/low will be loaded from Hammer snapshots asynchronously.
    This function just initializes the engine - snapshot loading happens separately.
    """
    engine = get_ticker_alert_engine()
    logger.info("✅ TickerAlertEngine initialized (daily high/low will be loaded from snapshots)")


async def preload_daily_high_low_from_snapshots():
    """
    Preload daily high/low for all symbols from Hammer snapshots (startup, ONCE).
    
    This function should be called after Hammer connects and CSV is loaded.
    It will enqueue snapshot requests for all symbols and cache daily high/low.
    """
    from app.api.market_data_routes import static_store, ETF_TICKERS
    from app.live.snapshot_queue import enqueue_snapshot
    from app.market_data.ticker_alert_engine import get_ticker_alert_engine
    
    engine = get_ticker_alert_engine()
    
    # Get all symbols (preferred stocks + ETFs)
    all_symbols = []
    
    # Add preferred stocks from CSV
    if static_store and static_store.is_loaded():
        preferred_symbols = static_store.get_all_symbols()
        all_symbols.extend(preferred_symbols)
        logger.info(f"📊 Will preload daily high/low for {len(preferred_symbols)} preferred stocks")
    
    # Add ETFs
    all_symbols.extend(ETF_TICKERS)
    logger.info(f"📊 Will preload daily high/low for {len(ETF_TICKERS)} ETFs")
    
    total_symbols = len(all_symbols)
    logger.info(f"📊 Total symbols to preload daily high/low: {total_symbols}")
    
    # Enqueue snapshot requests with callback to cache daily high/low
    # Create callback factory to capture symbol
    def create_snapshot_callback(symbol: str):
        """Create callback for a specific symbol"""
        def snapshot_callback(snapshot_dict: Dict[str, Any]):
            """Callback when snapshot is ready - cache daily high/low"""
            if not snapshot_dict:
                return
            
            daily_high = snapshot_dict.get('high')
            daily_low = snapshot_dict.get('low')
            
            if daily_high and daily_high > 0 and daily_low and daily_low > 0:
                engine.load_daily_high_low_from_snapshot(symbol, daily_high, daily_low)
                logger.debug(f"✅ Cached daily high/low for {symbol}: high={daily_high}, low={daily_low}")
            else:
                logger.debug(f"⚠️ Snapshot for {symbol} missing high/low: high={daily_high}, low={daily_low}")
        
        return snapshot_callback
    
    # Enqueue all symbols (snapshot queue will handle rate limiting and deduplication)
    enqueued_count = 0
    for symbol in all_symbols:
        # Enqueue with symbol-specific callback
        callback = create_snapshot_callback(symbol)
        if enqueue_snapshot(symbol, callback=callback):
            enqueued_count += 1
    
    logger.info(f"📊 Enqueued {enqueued_count} snapshot requests for daily high/low preload")
    return enqueued_count
