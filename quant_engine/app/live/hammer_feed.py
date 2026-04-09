"""app/live/hammer_feed.py

Hammer Feed wrapper for market data subscriptions.
Provides batch subscription methods for preferred stocks and ETFs.
"""

import time
from typing import List, Optional, Dict, Any
from app.core.logger import logger
from app.live.symbol_mapper import SymbolMapper


class HammerFeed:
    """
    Wrapper for HammerClient that provides feed-like interface.
    
    Handles batch subscriptions and symbol formatting.
    Processes L1Update messages and updates market data cache.
    """
    
    def __init__(self, hammer_client):
        """
        Initialize HammerFeed.
        
        Args:
            hammer_client: HammerClient instance
        """
        self.hammer_client = hammer_client
        
        # Set message callback to handle L1Update messages
        self.hammer_client.on_message_callback = self._handle_message
        
        logger.info("HammerFeed initialized")
    
    def _handle_message(self, data: Dict[str, Any]):
        """
        Handle incoming Hammer Pro messages.
        
        Processes L1Update messages and updates market data cache.
        
        Args:
            data: Message data from Hammer Pro
        """
        if not hasattr(self, '_recent_ticks'):
            self._recent_ticks = {}
            self._last_volatility_check = 0
            self._last_macro_volatility_log = 0.0  # Volatilite uyarilarini throttle etmek icin
            
        try:
            cmd = data.get("cmd", "")
            
            # Debug: Log first few messages to verify callback is working
            if not hasattr(self, '_msg_count'):
                self._msg_count = 0
            self._msg_count += 1
            if self._msg_count <= 5:
                logger.debug(f"📥 HammerFeed message #{self._msg_count}: cmd={cmd}")
            
            # Handle L1Update messages (bid/ask/last updates)
            if cmd == "L1Update":
                result = data.get("result", {})
                if not result:
                    return
                
                # Get symbol in Hammer format (e.g., "CIM-B", "SPY")
                hammer_symbol = result.get("sym")
                if not hammer_symbol:
                    return
                
                # Convert to display format (e.g., "CIM PRB", "SPY")
                display_symbol = SymbolMapper.to_display_symbol(hammer_symbol)
                
                # Debug: Log raw L1Update message for first few messages
                if not hasattr(self, '_raw_l1update_logged'):
                    self._raw_l1update_logged = 0
                self._raw_l1update_logged += 1
                if self._raw_l1update_logged <= 3:
                    logger.info(f"🔍 Raw L1Update #{self._raw_l1update_logged} for {display_symbol}: {result}")
                
                # Extract market data - check multiple possible field names
                bid = result.get("bid")
                ask = result.get("ask")
                last = result.get("last") or result.get("price") or result.get("trade") or result.get("tradePrice")
                volume = result.get("volume")
                size = result.get("size")
                venue = result.get("venue") or result.get("exchange")  # FNRA, NYSE, ARCA, etc.
                
                # If size > 0, this is a trade and last should be set
                if size and float(size) > 0 and last is None:
                    # Try to get last from price field or use bid/ask midpoint as last trade
                    price = result.get("price")
                    if price:
                        last = price
                    elif bid and ask:
                        # If no explicit last, use bid/ask midpoint for trade
                        last = (float(bid) + float(ask)) / 2.0
                        logger.debug(f"📊 {display_symbol}: Using bid/ask midpoint as last (size={size})")
                
                # Skip if no valid data
                if bid is None and ask is None and last is None:
                    return
                
                    # Build market data dict
                import time
                now = time.time()
                market_data = {
                    "bid": float(bid) if bid is not None and bid != "" else None,
                    "ask": float(ask) if ask is not None and ask != "" else None,
                    "last": float(last) if last is not None and last != "" else None,
                    "volume": float(volume) if volume is not None and volume != "" else None,
                    "size": float(size) if size is not None and size != "" else None,
                    "venue": str(venue) if venue is not None and venue != "" else None,
                    "timestamp": now,  # Unix timestamp for TTL validation
                }
                
                try:
                    from app.api.market_data_routes import update_market_data_cache, update_etf_market_data, ETF_TICKERS
                    
                    # 🔴 V.I.P ETF PROCESSING LANE (Absolute Priority) 🔴
                    if display_symbol in ETF_TICKERS:
                        if not hasattr(self, '_etf_update_count'):
                            self._etf_update_count = 0
                        self._etf_update_count += 1
                        if self._etf_update_count <= 20:
                            logger.info(f"⚡ [VIP_ETF_LANE] L1Update #{self._etf_update_count}: {display_symbol} bid={bid} ask={ask} last={last}")
                        
                        update_etf_market_data(display_symbol, market_data)
                        
                        try:
                            from app.core.benchmark_store import get_benchmark_store
                            benchmark_store = get_benchmark_store()
                            if benchmark_store and last is not None:
                                benchmark_store.update_from_l1(display_symbol, float(last))
                        except Exception:
                            pass
                            
                        # Immediately alert ETF_GUARD
                        try:
                            from app.terminals.etf_guard_terminal import get_etf_guard
                            guard = get_etf_guard()
                            if guard:
                                # Send ETF update directly to force micro-trigger check on this exact tick
                                guard.process_vip_tick(display_symbol, market_data)
                        except Exception as e:
                            pass
                            
                    else:
                        # Standard Lane (Preferred Stocks)
                        update_market_data_cache(display_symbol, market_data)
                        
                        # 🔴 MACRO-VOLATILITY DETECTION 🔴
                        # Track recent preferred stock ticks for volatility spikes
                        self._recent_ticks[display_symbol] = now
                        
                        # Only run expensive volatility check every 500ms
                        if now - self._last_volatility_check > 0.5:
                            self._last_volatility_check = now
                            
                            cutoff_5s = now - 5.0
                            cutoff_2s = now - 2.0
                            
                            active_5s = 0
                            active_2s = 0
                            
                            for sym in list(self._recent_ticks.keys()):
                                tick_time = self._recent_ticks[sym]
                                if tick_time < cutoff_5s:
                                    del self._recent_ticks[sym]
                                else:
                                    active_5s += 1
                                    if tick_time >= cutoff_2s:
                                        active_2s += 1
                            
                            if active_2s >= 15 or active_5s >= 25:
                                if now - self._last_macro_volatility_log >= 2.0:
                                    logger.warning(f"🚨 [MACRO-VOLATILITE] 2sn:{active_2s} | 5sn:{active_5s} Ticker bid/ask degisti! VIP ETF Guard devrede!")
                                    self._last_macro_volatility_log = now
                                try:
                                    from app.terminals.etf_guard_terminal import get_etf_guard
                                    guard = get_etf_guard()
                                    if guard:
                                        # Force a complete re-evaluation
                                        guard._execute_safeguard_checks()
                                except Exception as e:
                                    logger.error(f"Error triggering ETF Guard during volatility: {e}")
                        
                        # =====================================================
                        # SECURITY REGISTRY UPDATE (hot-path - minimal work)
                        # =====================================================
                        try:
                            from app.core.security_registry import get_security_registry
                            registry = get_security_registry()
                            if registry:
                                ctx = registry.resolve_and_get(display_symbol)
                                if ctx:
                                    ctx.update_l1(
                                        bid=market_data.get("bid"),
                                        ask=market_data.get("ask"),
                                        last=market_data.get("last"),
                                        volume=int(market_data.get("volume")) if market_data.get("volume") else None,
                                        source="HAMMER"
                                    )
                        except Exception:
                            pass

                    # Log first few L1Updates at INFO level
                    if not hasattr(self, '_l1update_count'):
                        self._l1update_count = 0
                    self._l1update_count += 1
                    if self._l1update_count <= 20:
                        logger.info(f"📊 [HAMMER_FEED] L1Update #{self._l1update_count}: {display_symbol} bid={bid} ask={ask} last={last} -> Cache Updated")
                except Exception as e:
                    logger.error(f"Error updating market data cache for {display_symbol}: {e}", exc_info=True)
            
        except Exception as e:
            logger.error(f"Error handling Hammer message: {e}", exc_info=True)
    
    def subscribe_symbol(self, symbol: str, include_l2: bool = False) -> bool:
        """
        Subscribe to a single symbol.
        
        Args:
            symbol: Display format symbol (e.g., "CIM PRB", "SPY")
            include_l2: If True, also subscribe to L2 (orderbook)
            
        Returns:
            True if subscription successful
        """
        if not self.hammer_client or not self.hammer_client.is_connected():
            logger.warning(f"Hammer client not connected, cannot subscribe to {symbol}")
            return False
        
        try:
            # Convert to Hammer format
            hammer_symbol = SymbolMapper.to_hammer_symbol(symbol)
            
            # Subscribe to L1 (bid/ask/last)
            l1_cmd = {
                "cmd": "subscribe",
                "sub": "L1",
                "streamerID": self.hammer_client.streamer_id,
                "sym": [hammer_symbol],
                "transient": False
            }
            
            if not self.hammer_client.send_command(l1_cmd, wait_for_response=False):
                logger.warning(f"Failed to subscribe to L1 for {symbol}")
                return False
            
            # Subscribe to L2 if requested
            if include_l2:
                l2_cmd = {
                    "cmd": "subscribe",
                    "sub": "L2",
                    "streamerID": self.hammer_client.streamer_id,
                    "sym": [hammer_symbol],
                    "transient": False
                }
                
                if not self.hammer_client.send_command(l2_cmd, wait_for_response=False):
                    logger.warning(f"Failed to subscribe to L2 for {symbol}")
                    # L1 subscription succeeded, so return True
                    return True
            
            logger.debug(f"✅ Subscribed to {symbol} (L1{' + L2' if include_l2 else ''})")
            return True
            
        except Exception as e:
            logger.error(f"Error subscribing to {symbol}: {e}", exc_info=True)
            return False
    
    def subscribe_symbols_batch(
        self,
        symbols: List[str],
        include_l2: bool = False,
        batch_size: int = 50
    ) -> int:
        """
        Subscribe to multiple symbols in batches.
        
        Args:
            symbols: List of display format symbols
            include_l2: If True, also subscribe to L2 (orderbook)
            batch_size: Number of symbols per batch (default: 20 to avoid connection issues)
            
        Returns:
            Number of successfully subscribed symbols
        """
        if not self.hammer_client or not self.hammer_client.is_connected():
            logger.warning("Hammer client not connected, cannot subscribe to symbols")
            return 0
        
        subscribed_count = 0
        
        # Process in batches
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            
            # Check connection before each batch
            if not self.hammer_client.is_connected():
                logger.warning(f"⚠️ Connection lost during subscription. Subscribed {subscribed_count}/{len(symbols)} so far.")
                break
            
            try:
                # Convert all symbols to Hammer format
                hammer_symbols = [SymbolMapper.to_hammer_symbol(s) for s in batch]
                
                # Subscribe to L1
                l1_cmd = {
                    "cmd": "subscribe",
                    "sub": "L1",
                    "streamerID": self.hammer_client.streamer_id,
                    "sym": hammer_symbols,
                    "transient": False
                }
                
                if self.hammer_client.send_command(l1_cmd, wait_for_response=False):
                    subscribed_count += len(batch)
                    logger.debug(f"✅ Subscribed to L1 batch: {len(batch)} symbols (total: {subscribed_count}/{len(symbols)})")
                else:
                    logger.warning(f"⚠️ Failed to subscribe to L1 batch: {len(batch)} symbols")
                    # If send fails, connection might be broken - break to avoid more failures
                    if not self.hammer_client.is_connected():
                        break
                
                # Subscribe to L2 if requested
                if include_l2:
                    # Small delay between L1 and L2
                    time.sleep(0.05)
                    
                    l2_cmd = {
                        "cmd": "subscribe",
                        "sub": "L2",
                        "streamerID": self.hammer_client.streamer_id,
                        "sym": hammer_symbols,
                        "transient": False
                    }
                    
                    if not self.hammer_client.send_command(l2_cmd, wait_for_response=False):
                        logger.warning(f"⚠️ Failed to subscribe to L2 batch: {len(batch)} symbols")
                        if not self.hammer_client.is_connected():
                            break
                
                # Longer delay between batches to avoid overwhelming Hammer
                if i + batch_size < len(symbols):
                    time.sleep(0.3)  # Increased from 0.1 to 0.3 seconds
                    
            except Exception as e:
                logger.error(f"Error subscribing to batch: {e}", exc_info=True)
                # Check if connection is still alive
                if not self.hammer_client.is_connected():
                    break
                continue
        
        logger.info(f"✅ Batch subscription complete: {subscribed_count}/{len(symbols)} symbols (L1{' + L2' if include_l2 else ''})")
        return subscribed_count


# ============================================================================
# GLOBAL SINGLETON INSTANCE
# ============================================================================
_hammer_feed_instance: Optional[HammerFeed] = None


def get_hammer_feed() -> Optional[HammerFeed]:
    """
    Get the global HammerFeed singleton instance.
    
    Returns:
        HammerFeed instance if initialized, None otherwise
    """
    return _hammer_feed_instance


def set_hammer_feed(instance: HammerFeed) -> None:
    """
    Set the global HammerFeed singleton instance.
    
    Args:
        instance: HammerFeed instance to set as global
    """
    global _hammer_feed_instance
    _hammer_feed_instance = instance
    logger.info("✅ Global HammerFeed instance set")
