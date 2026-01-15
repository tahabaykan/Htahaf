"""app/engine/live_engine.py

Live trading engine - processes market data and manages orders.
Stateful, order-aware algorithm for preferred stock trading.

Market data ALWAYS from Hammer (single source of truth).
Execution is pluggable via ExecutionAdapter (IBKR | HAMMER).
"""

from typing import Dict, Any, Optional, Callable
from datetime import datetime

from app.core.logger import logger
from app.live.execution_adapter import ExecutionAdapter

# Optional import - HammerFeed may not be available
try:
    from app.live.hammer_feed import HammerFeed
except ImportError:
    HammerFeed = None
from app.engine.position_manager import PositionManager
from app.risk.risk_manager import RiskManager


class LiveEngine:
    """
    Live trading engine.
    
    Responsibilities:
    - Process market data (ticks, order books) - ALWAYS from Hammer
    - Manage orders (place, cancel, replace) - via ExecutionAdapter
    - Track positions
    - Apply risk checks
    - Execute trading logic
    
    This is where your trading strategy lives.
    
    Key Architecture:
    - Market Data: Hammer ONLY (single source of truth)
    - Execution: Pluggable (IBKR | HAMMER) via ExecutionAdapter
    - Strategy: Broker-agnostic
    """
    
    def __init__(
        self,
        hammer_feed: HammerFeed,
        execution_adapter: ExecutionAdapter,
        position_manager: Optional[PositionManager] = None,
        risk_manager: Optional[RiskManager] = None
    ):
        """
        Initialize live engine.
        
        Args:
            hammer_feed: Market data feed handler (ALWAYS Hammer)
            execution_adapter: Execution adapter (IBKR or HAMMER)
            position_manager: Position manager (optional)
            risk_manager: Risk manager (optional)
        """
        self.feed = hammer_feed
        self.execution = execution_adapter  # Now uses ExecutionAdapter interface
        self.position_manager = position_manager or PositionManager()
        self.risk_manager = risk_manager
        
        # Set engine callbacks
        self.feed.engine_callback = self._on_feed_event
        self.execution.set_execution_callback(self._on_execution)
        
        # State tracking
        self.open_orders: Dict[str, Dict[str, Any]] = {}
        self.last_tick: Dict[str, Dict[str, Any]] = {}
        self.last_orderbook: Dict[str, Dict[str, Any]] = {}
        
        logger.info(
            f"LiveEngine initialized | "
            f"Execution: {execution_adapter.broker.value} "
            f"(account: {execution_adapter.account_id})"
        )
    
    def _on_feed_event(self, event_type: str, data: Dict[str, Any]):
        """Handle feed events (tick or orderbook)"""
        try:
            if event_type == "tick":
                self.on_tick(data)
            elif event_type == "orderbook":
                self.on_orderbook(data)
        except Exception as e:
            logger.error(f"Error in feed event handler: {e}", exc_info=True)
    
    def _on_execution(self, execution: Dict[str, Any]):
        """Handle execution (fill)"""
        try:
            self.on_execution(execution)
        except Exception as e:
            logger.error(f"Error in execution handler: {e}", exc_info=True)
    
    def on_tick(self, tick: Dict[str, Any]):
        """
        Process tick data.
        
        This is where your trading logic goes.
        
        Args:
            tick: Tick data dictionary
        """
        symbol = tick.get("symbol")
        if not symbol:
            return
        
        # Store last tick
        self.last_tick[symbol] = tick
        
        # Calculate spread
        bid = tick.get("bid", 0)
        ask = tick.get("ask", 0)
        last = tick.get("last", 0)
        
        if bid > 0 and ask > 0:
            spread = ask - bid
            mid = (bid + ask) / 2
            spread_pct = (spread / mid * 100) if mid > 0 else 0
            
            # Log tick (for testing) - only on trades or significant updates
            if tick.get("is_trade") or symbol not in self.last_tick:
                logger.info(
                    f"🎯 TICK: {symbol} | "
                    f"Last: ${last:.2f} | "
                    f"Bid: ${bid:.2f} | "
                    f"Ask: ${ask:.2f} | "
                    f"Spread: ${spread:.2f} ({spread_pct:.2f}%) | "
                    f"Size: {tick.get('size', 0)}"
                )
                
                # Warn if spread is too wide (for preferred stocks)
                if spread_pct > 1.0:  # 1% threshold
                    logger.warning(f"⚠️ Wide spread detected: {symbol} spread={spread_pct:.2f}%")
        
        # TODO: Add your trading logic here
        # Example:
        # - Check spread
        # - Check liquidity
        # - Generate signals
        # - Place/cancel orders
    
    def on_orderbook(self, orderbook: Dict[str, Any]):
        """
        Process order book update.
        
        Args:
            orderbook: Order book data dictionary
        """
        symbol = orderbook.get("symbol")
        if not symbol:
            return
        
        # Store last orderbook
        self.last_orderbook[symbol] = orderbook
        
        # Log orderbook (for testing)
        bids = orderbook.get("bids", [])
        asks = orderbook.get("asks", [])
        if bids and asks:
            best_bid = bids[0]["price"]
            best_ask = asks[0]["price"]
            spread = best_ask - best_bid
            spread_pct = (spread / best_bid * 100) if best_bid > 0 else 0
            
            logger.info(
                f"ORDERBOOK: {symbol} | Bid: ${best_bid:.2f} | Ask: ${best_ask:.2f} | "
                f"Spread: ${spread:.2f} ({spread_pct:.2f}%)"
            )
        
        # TODO: Add your order book logic here
        # Example:
        # - Analyze depth
        # - Check liquidity
        # - Adjust order prices
    
    def on_execution(self, execution: Dict[str, Any]):
        """
        Process execution (fill).
        
        Args:
            execution: Execution data dictionary
        """
        symbol = execution.get("symbol")
        side = execution.get("side")
        qty = execution.get("fill_qty")
        price = execution.get("fill_price")
        
        logger.info(
            f"EXECUTION: {symbol} | {side} {qty} @ ${price:.2f}"
        )
        
        # Update position manager
        exec_msg = {
            "symbol": symbol,
            "side": side,
            "fill_qty": qty,
            "fill_price": price,
            "timestamp": execution.get("timestamp")
        }
        
        self.position_manager.apply_execution(exec_msg)
        
        # Update risk manager
        if self.risk_manager:
            self.risk_manager.update_after_execution(symbol, side, qty, price)
        
        # TODO: Add your execution logic here
        # Example:
        # - Update strategy state
        # - Adjust position sizing
        # - Generate follow-up orders
    
    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        order_type: str = "LIMIT"
    ) -> bool:
        """
        Place order through execution handler.
        
        Args:
            symbol: Display format symbol
            side: "BUY" or "SELL"
            quantity: Order quantity
            price: Limit price
            order_type: "LIMIT" or "MARKET"
            
        Returns:
            True if order placed successfully
        """
        # Risk check
        if self.risk_manager:
            # TODO: Add risk checks here
            pass
        
        # Place order
        return self.execution.place_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            price=price,
            order_type=order_type
        )
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel order"""
        return self.execution.cancel_order(order_id)
    
    def get_positions(self) -> list:
        """Get current positions"""
        return self.execution.get_positions()
    
    def subscribe_symbols(self, symbols: list, include_l2: bool = True):
        """
        Subscribe to multiple symbols.
        
        Args:
            symbols: List of display format symbols
            include_l2: If True, also subscribe to L2
        """
        for symbol in symbols:
            self.feed.subscribe_symbol(symbol, include_l2=include_l2)

