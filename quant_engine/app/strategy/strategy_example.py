"""app/strategy/strategy_example.py

Example strategy implementation - demonstrates strategy framework usage.
"""

from typing import Dict, Any, Optional, List

from app.strategy.strategy_base import StrategyBase
from app.core.logger import logger
from app.order.order_publisher import OrderPublisher


class ExampleStrategy(StrategyBase):
    """
    Example strategy - simple moving average crossover.
    
    Strategy logic:
    - Buy when price crosses above SMA(20)
    - Sell when price crosses below SMA(20)
    """
    
    def __init__(self):
        super().__init__(name="ExampleStrategy")
        self.sma_period = 20
        self.last_signal = {}  # Track last signal per symbol to avoid duplicates
    
    def on_initialize(self):
        """Strategy-specific initialization"""
        logger.info(f"ExampleStrategy initialized with SMA period: {self.sma_period}")
    
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
        Strategy logic implementation.
        
        Simple SMA crossover strategy.
        """
        try:
            # Get current position
            current_qty = position.get('qty', 0) if position else 0
            
            # Calculate SMA
            sma = self.get_indicator(symbol, 'sma', period=self.sma_period)
            if sma is None:
                return None  # Not enough data
            
            # Get previous price for crossover detection
            candles = self.get_candles(symbol, count=2)
            if len(candles) < 2:
                return None
            
            prev_price = candles[-2]['close']
            current_price = candles[-1]['close'] if candles else price
            
            # Crossover detection
            signal = None
            
            # Bullish crossover: price crosses above SMA
            if prev_price <= sma and current_price > sma:
                if current_qty <= 0:  # Not long or flat
                    signal = {
                        'symbol': symbol,
                        'signal': 'BUY',
                        'price': current_price,
                        'quantity': 10,  # Fixed quantity
                        'order_type': 'MKT',
                        'reason': f'Bullish crossover: price {current_price:.2f} > SMA {sma:.2f}'
                    }
            
            # Bearish crossover: price crosses below SMA
            elif prev_price >= sma and current_price < sma:
                if current_qty > 0:  # Long position
                    signal = {
                        'symbol': symbol,
                        'signal': 'SELL',
                        'price': current_price,
                        'quantity': abs(current_qty),  # Close position
                        'order_type': 'MKT',
                        'reason': f'Bearish crossover: price {current_price:.2f} < SMA {sma:.2f}'
                    }
            
            if signal:
                # Avoid duplicate signals
                last_signal_key = f"{symbol}_{signal['signal']}"
                if last_signal_key in self.last_signal:
                    # Only signal if enough time passed (e.g., 1 minute)
                    import time
                    if time.time() - self.last_signal[last_signal_key] < 60:
                        return None
                
                self.last_signal[last_signal_key] = time.time()
                
                # Publish order directly (optional - can also return signal)
                try:
                    if signal['order_type'] == 'MKT':
                        OrderPublisher.publish_market_order(
                            signal['symbol'],
                            signal['signal'],
                            signal['quantity']
                        )
                    else:
                        OrderPublisher.publish_limit_order(
                            signal['symbol'],
                            signal['signal'],
                            signal['quantity'],
                            signal.get('limit_price', signal['price'])
                        )
                    
                    logger.info(f"Order published: {signal}")
                    return signal
                
                except Exception as e:
                    logger.error(f"Error publishing order: {e}")
                    return signal
            
            return None
        
        except Exception as e:
            logger.error(f"Error in strategy logic: {e}", exc_info=True)
            return None
