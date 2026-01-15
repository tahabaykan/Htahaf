"""app/strategy/strategy_base.py

Base strategy class - all strategies should inherit from this.

This class provides the foundation for event-driven, multi-symbol strategies
with indicator support, candle data, and risk guards.
"""

from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod

from app.core.logger import logger
from app.strategy.indicators import Indicators, indicator_cache
from app.strategy.candle_manager import CandleManager
from app.engine.position_manager import PositionManager
from app.engine.risk_manager import RiskManager


class StrategyBase(ABC):
    """
    Base class for all trading strategies.
    
    Provides:
    - Indicator calculations
    - Candle/OHLCV data
    - Position tracking
    - Risk management
    - Event-driven architecture
    """
    
    def __init__(self, name: str = "BaseStrategy"):
        """
        Initialize strategy.
        
        Args:
            name: Strategy name
        """
        self.name = name
        self.initialized = False
        
        # Components
        self.candle_manager: Optional[CandleManager] = None
        self.position_manager: Optional[PositionManager] = None
        self.risk_manager: Optional[RiskManager] = None
        
        # Configuration
        self.symbols: List[str] = []  # Symbols to trade
        self.candle_interval: int = 60  # Candle interval in seconds
        
        # State
        self.tick_count = 0
        self.signal_count = 0
    
    def initialize(
        self,
        candle_manager: Optional[CandleManager] = None,
        position_manager: Optional[PositionManager] = None,
        risk_manager: Optional[RiskManager] = None,
        symbols: Optional[List[str]] = None
    ):
        """
        Initialize strategy with dependencies.
        
        Args:
            candle_manager: CandleManager instance
            position_manager: PositionManager instance
            risk_manager: RiskManager instance
            symbols: List of symbols to trade
        """
        self.candle_manager = candle_manager or CandleManager(interval_seconds=self.candle_interval)
        self.position_manager = position_manager
        self.risk_manager = risk_manager
        
        if symbols:
            self.symbols = symbols
        
        self.initialized = True
        logger.info(f"Strategy {self.name} initialized (symbols: {self.symbols})")
        
        # Call strategy-specific initialization
        self.on_initialize()
    
    def on_initialize(self):
        """
        Strategy-specific initialization (override in subclass).
        Called after strategy is initialized.
        """
        pass
    
    def on_tick(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process tick data (main entry point).
        
        This method:
        1. Updates candle data
        2. Calculates indicators
        3. Calls strategy logic
        4. Generates signals
        
        Args:
            tick: Tick data dict (symbol, last, bid, ask, volume, ts)
            
        Returns:
            Signal dict or None
        """
        if not self.initialized:
            logger.warning(f"Strategy {self.name} not initialized")
            return None
        
        try:
            symbol = tick.get('symbol')
            if not symbol:
                return None
            
            self.tick_count += 1
            
            # Update candle data
            completed_candle = None
            if self.candle_manager:
                completed_candle = self.candle_manager.add_tick(tick)
            
            # Get current price
            price = float(tick.get('last', 0))
            if price <= 0:
                return None
            
            # Get current position
            position = None
            if self.position_manager:
                position = self.position_manager.get_position(symbol)
            
            # Get candle data for indicators
            candle_data = None
            if self.candle_manager:
                candle_data = self.candle_manager.get_candle_data(symbol, count=100)
            
            # Call strategy logic
            signal = self.on_market_data(
                symbol=symbol,
                price=price,
                tick=tick,
                position=position,
                candle_data=candle_data,
                completed_candle=completed_candle
            )
            
            if signal:
                self.signal_count += 1
                # Apply risk checks
                if self.risk_manager:
                    # Extract order details from signal
                    symbol = signal.get('symbol')
                    side = signal.get('signal', 'BUY')  # signal field = BUY/SELL
                    qty = float(signal.get('quantity', signal.get('qty', 0)))
                    price = float(signal.get('price', 0))
                    
                    allowed, reason = self.risk_manager.check_before_order(symbol, side, qty, price)
                    if not allowed:
                        logger.warning(f"Signal rejected by risk manager: {reason}")
                        return None
                
                return signal
            
            return None
        
        except Exception as e:
            logger.error(f"Error in strategy on_tick: {e}", exc_info=True)
            return None
    
    @abstractmethod
    def on_market_data(
        self,
        symbol: str,
        price: float,
        tick: Dict[str, Any],
        position: Optional[Dict],
        candle_data: Optional[Dict[str, List[float]]],
        completed_candle: Optional[Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Strategy logic - implement in subclass.
        
        Args:
            symbol: Stock symbol
            price: Current price
            tick: Full tick data
            position: Current position dict (or None)
            candle_data: Candle data dict with 'open', 'high', 'low', 'close', 'volume' lists
            completed_candle: Just completed candle (or None)
            
        Returns:
            Signal dict or None
            
        Signal format:
            {
                'symbol': str,
                'signal': 'BUY' | 'SELL',
                'price': float,
                'quantity': int (optional),
                'order_type': 'MKT' | 'LMT' (optional, default: 'MKT'),
                'limit_price': float (optional, for LMT),
                'reason': str (optional)
            }
        """
        raise NotImplementedError("Subclass must implement on_market_data")
    
    def get_indicator(self, symbol: str, indicator_name: str, **kwargs) -> Optional[float]:
        """
        Get indicator value (with caching).
        
        Args:
            symbol: Stock symbol
            indicator_name: Indicator name ('sma', 'ema', 'rsi', etc.)
            **kwargs: Indicator parameters
            
        Returns:
            Indicator value or None
        """
        try:
            candle_data = self.candle_manager.get_candle_data(symbol) if self.candle_manager else None
            if not candle_data or not candle_data.get('close'):
                return None
            
            prices = candle_data['close']
            
            if indicator_name.lower() == 'sma':
                period = kwargs.get('period', 20)
                value = Indicators.sma(prices, period)
            elif indicator_name.lower() == 'ema':
                period = kwargs.get('period', 20)
                value = Indicators.ema(prices, period)
            elif indicator_name.lower() == 'rsi':
                period = kwargs.get('period', 14)
                value = Indicators.rsi(prices, period)
            else:
                logger.warning(f"Unknown indicator: {indicator_name}")
                return None
            
            # Cache value
            if value is not None:
                indicator_cache.add_value(symbol, indicator_name, value)
            
            return value
        
        except Exception as e:
            logger.error(f"Error calculating indicator: {e}")
            return None
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get current position for symbol"""
        if self.position_manager:
            return self.position_manager.get_position(symbol)
        return None
    
    def get_candles(self, symbol: str, count: int = 100) -> List[Dict[str, Any]]:
        """Get candle history for symbol"""
        if self.candle_manager:
            candles = self.candle_manager.get_candles(symbol, count)
            return [c.to_dict() for c in candles]
        return []
    
    def on_signal(self, signal: Dict[str, Any]):
        """
        Called when a signal is generated (optional override).
        
        Args:
            signal: Signal dict
        """
        logger.debug(f"Signal generated: {signal}")
    
    def cleanup(self):
        """Cleanup strategy (called on shutdown)"""
        logger.info(f"Strategy {self.name} cleanup")
    
    def risk_allowed(self, symbol: str, side: str, qty: float, price: float) -> bool:
        """
        Check if order is allowed by risk manager.
        
        Args:
            symbol: Stock symbol
            side: BUY or SELL
            qty: Order quantity
            price: Order price
            
        Returns:
            True if allowed, False otherwise
        """
        if not self.risk_manager:
            return True  # No risk manager = allow all
        
        allowed, reason = self.risk_manager.check_before_order(symbol, side, qty, price)
        if not allowed:
            logger.debug(f"Risk check failed: {reason}")
        return allowed
    
    def get_stats(self) -> Dict[str, Any]:
        """Get strategy statistics"""
        return {
            'name': self.name,
            'tick_count': self.tick_count,
            'signal_count': self.signal_count,
            'symbols': self.symbols,
            'initialized': self.initialized
        }
