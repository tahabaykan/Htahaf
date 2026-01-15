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
                market_data = {
                    "bid": float(bid) if bid is not None and bid != "" else None,
                    "ask": float(ask) if ask is not None and ask != "" else None,
                    "last": float(last) if last is not None and last != "" else None,
                    "volume": float(volume) if volume is not None and volume != "" else None,
                    "size": float(size) if size is not None and size != "" else None,
                }
                
                # Update market data cache
                try:
                    from app.api.market_data_routes import update_market_data_cache, update_etf_market_data, ETF_TICKERS
                    
                    # Check if it's an ETF
                    if display_symbol in ETF_TICKERS:
                        # Log ETF updates at INFO level to verify they're being received
                        if not hasattr(self, '_etf_update_count'):
                            self._etf_update_count = 0
                        self._etf_update_count += 1
                        if self._etf_update_count <= 20:
                            logger.info(f"📊 ETF L1Update #{self._etf_update_count}: {display_symbol} (hammer={hammer_symbol}) bid={bid} ask={ask} last={last}")
                        else:
                            logger.debug(f"📊 ETF L1Update: {display_symbol} (hammer={hammer_symbol}) bid={bid} ask={ask} last={last}")
                        update_etf_market_data(display_symbol, market_data)
                    else:
                        update_market_data_cache(display_symbol, market_data)
                    
                    # Log first few L1Updates at INFO level to verify they're being received
                    if not hasattr(self, '_l1update_count'):
                        self._l1update_count = 0
                    self._l1update_count += 1
                    if self._l1update_count <= 10:
                        logger.info(f"📊 L1Update #{self._l1update_count}: {display_symbol} bid={bid} ask={ask} last={last}")
                    else:
                        logger.debug(f"📊 L1Update: {display_symbol} bid={bid} ask={ask} last={last}")
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
                "streamerID": "ALARICQ",
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
                    "streamerID": "ALARICQ",
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
                    "streamerID": "ALARICQ",
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
                        "streamerID": "ALARICQ",
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
