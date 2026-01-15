"""
Take Profit Engine - Long and Short Position Management

Handles take profit order generation for existing positions
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field, asdict

from app.core.logger import logger


@dataclass
class TakeProfitPosition:
    """Take Profit Position"""
    symbol: str
    quantity: int
    avg_price: float
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    lrpan_price: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TakeProfitEngine:
    """
    Take Profit Engine
    
    Manages take profit orders for long and short positions
    """
    
    def __init__(self):
        logger.info("[TAKE_PROFIT] Engine initialized")
    
    def get_long_positions(self) -> List[TakeProfitPosition]:
        """
        Get long positions (quantity > 0)
        
        Returns:
            List of long positions
        """
        try:
            from app.psfalgo.position_snapshot_api import get_position_snapshot_api
            
            position_api = get_position_snapshot_api()
            if not position_api:
                logger.warning("[TAKE_PROFIT] PositionSnapshotAPI not available")
                return []
            
            snapshot = position_api.get_position_snapshot()
            if not snapshot:
                return []
            
            # Get market data for positions
            from app.core.data_fabric import get_data_fabric
            data_fabric = get_data_fabric()
            
            long_positions = []
            for pos in snapshot.positions:
                if pos.qty > 0:  # Long position
                    # Get market data
                    market_data = data_fabric.get_fast_snapshot(pos.symbol)
                    
                    position = TakeProfitPosition(
                        symbol=pos.symbol,
                        quantity=pos.qty,
                        avg_price=pos.avg_price or 0.0,
                        bid=market_data.get('bid', 0.0) if market_data else 0.0,
                        ask=market_data.get('ask', 0.0) if market_data else 0.0,
                        last=market_data.get('last', 0.0) if market_data else 0.0,
                        lrpan_price=self.get_lrpan_price(pos.symbol)
                    )
                    long_positions.append(position)
            
            logger.info(f"[TAKE_PROFIT] Found {len(long_positions)} long positions")
            return long_positions
            
        except Exception as e:
            logger.error(f"[TAKE_PROFIT] Error getting long positions: {e}", exc_info=True)
            return []
    
    def get_short_positions(self) -> List[TakeProfitPosition]:
        """
        Get short positions (quantity < 0)
        
        Returns:
            List of short positions
        """
        try:
            from app.psfalgo.position_snapshot_api import get_position_snapshot_api
            
            position_api = get_position_snapshot_api()
            if not position_api:
                logger.warning("[TAKE_PROFIT] PositionSnapshotAPI not available")
                return []
            
            snapshot = position_api.get_position_snapshot()
            if not snapshot:
                return []
            
            # Get market data for positions
            from app.core.data_fabric import get_data_fabric
            data_fabric = get_data_fabric()
            
            short_positions = []
            for pos in snapshot.positions:
                if pos.qty < 0:  # Short position
                    # Get market data
                    market_data = data_fabric.get_fast_snapshot(pos.symbol)
                    
                    position = TakeProfitPosition(
                        symbol=pos.symbol,
                        quantity=abs(pos.qty),  # Make positive for display
                        avg_price=pos.avg_price or 0.0,
                        bid=market_data.get('bid', 0.0) if market_data else 0.0,
                        ask=market_data.get('ask', 0.0) if market_data else 0.0,
                        last=market_data.get('last', 0.0) if market_data else 0.0,
                        lrpan_price=self.get_lrpan_price(pos.symbol)
                    )
                    short_positions.append(position)
            
            logger.info(f"[TAKE_PROFIT] Found {len(short_positions)} short positions")
            return short_positions
            
        except Exception as e:
            logger.error(f"[TAKE_PROFIT] Error getting short positions: {e}", exc_info=True)
            return []
    
    def calculate_take_profit_price(
        self,
        order_type: str,
        bid: float,
        ask: float,
        last: float
    ) -> float:
        """
        Calculate take profit price based on order type
        
        Args:
            order_type: 'ASK_SELL', 'FRONT_SELL', 'SOFTFRONT_SELL', 'BID_SELL',
                       'BID_BUY', 'FRONT_BUY', 'SOFTFRONT_BUY', 'ASK_BUY'
            bid: Current bid price
            ask: Current ask price
            last: Last trade price
        
        Returns:
            Calculated price
        """
        if order_type == 'ASK_SELL':
            return ask
        elif order_type == 'FRONT_SELL':
            return last + 0.01
        elif order_type == 'SOFTFRONT_SELL':
            return last - 0.01
        elif order_type == 'BID_SELL':
            return bid
        elif order_type == 'BID_BUY':
            return bid
        elif order_type == 'FRONT_BUY':
            return last - 0.01
        elif order_type == 'SOFTFRONT_BUY':
            return last + 0.01
        elif order_type == 'ASK_BUY':
            return ask
        else:
            logger.warning(f"[TAKE_PROFIT] Unknown order type: {order_type}, using last")
            return last
    
    def divide_lot_size(self, total_lot: int) -> List[int]:
        """
        Divide lot size (Janall logic)
        
        - 0-399 lot: direkt
        - 400+: 200'ün katları + kalan
        
        Args:
            total_lot: Total lot size
        
        Returns:
            List of lot sizes
        """
        if total_lot <= 0:
            return []
        
        if total_lot <= 399:
            return [total_lot]
        
        lot_parts = []
        remaining = total_lot
        
        while remaining >= 400:
            lot_parts.append(200)
            remaining -= 200
        
        if remaining > 0:
            lot_parts.append(remaining)
        
        return lot_parts
    
    def check_soft_front_conditions(
        self,
        bid: float,
        ask: float,
        last_print: float,
        symbol: Optional[str] = None,
        is_buy: bool = True
    ) -> bool:
        """
        Check SoftFront Buy/Sell conditions (Janall logic)
        
        Args:
            bid: Current bid
            ask: Current ask
            last_print: Last print price
            symbol: Symbol (for LRPAN lookup)
            is_buy: True for buy, False for sell
        
        Returns:
            True if conditions met
        """
        if bid <= 0 or ask <= 0 or last_print <= 0:
            return False
        
        spread = ask - bid
        if spread <= 0:
            return False
        
        # Get LRPAN price if available
        lrpan_price = self.get_lrpan_price(symbol) if symbol else None
        
        if lrpan_price is None:
            real_print_price = last_print
        else:
            real_print_price = lrpan_price
        
        if is_buy:
            # SoftFront Buy: (ask - real_print_price) / spread > 0.60 OR (ask - real_print_price) >= 0.15
            condition1 = (ask - real_print_price) / spread > 0.60
            condition2 = (ask - real_print_price) >= 0.15
            return condition1 or condition2
        else:
            # SoftFront Sell: (real_print_price - bid) / spread > 0.60 OR (real_print_price - bid) >= 0.15
            condition1 = (real_print_price - bid) / spread > 0.60
            condition2 = (real_print_price - bid) >= 0.15
            return condition1 or condition2
    
    def get_lrpan_price(self, symbol: str) -> Optional[float]:
        """
        Get LRPAN price (100/200/300 lot prints)
        
        Args:
            symbol: Symbol to get LRPAN for
        
        Returns:
            LRPAN price or None
        """
        try:
            # This would require tick-by-tick data
            # For now, return None (will be implemented when tick data is available)
            return None
        except Exception as e:
            logger.debug(f"[TAKE_PROFIT] LRPAN price not available for {symbol}: {e}")
            return None


# Global instance
_take_profit_engine: Optional[TakeProfitEngine] = None


def get_take_profit_engine() -> Optional[TakeProfitEngine]:
    """Get global TakeProfitEngine instance"""
    return _take_profit_engine


def initialize_take_profit_engine() -> TakeProfitEngine:
    """Initialize global TakeProfitEngine instance"""
    global _take_profit_engine
    _take_profit_engine = TakeProfitEngine()
    logger.info("[TAKE_PROFIT] Engine initialized globally")
    return _take_profit_engine





