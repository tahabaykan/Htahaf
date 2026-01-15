"""
Trade Print Router
Normalizes trade prints from Hammer Time&Sales stream.

Single source of truth for trade print normalization:
- symbol, price, size, timestamp, trade_id
- Separated from L2Update and last price logic
"""

from typing import Dict, Any, Optional
from datetime import datetime
from app.core.logger import logger
from app.live.symbol_mapper import SymbolMapper


class TradePrintRouter:
    """
    Routes and normalizes trade prints from Hammer Pro.
    
    Responsibilities:
    - Normalize trade print format
    - Extract symbol, price, size, timestamp, trade_id
    - Forward to GRPANEngine
    """
    
    def __init__(self, grpan_engine):
        """
        Initialize trade print router.
        
        Args:
            grpan_engine: GRPANEngine instance
        """
        self.grpan_engine = grpan_engine
        self.print_count = 0
        self.error_count = 0
    
    def route_trade_print(self, raw_print: Dict[str, Any], hammer_symbol: str) -> Optional[Dict[str, Any]]:
        """
        Route and normalize a trade print from Hammer.
        
        Args:
            raw_print: Raw trade print from Hammer (dict or string)
            hammer_symbol: Symbol in Hammer format (e.g., "CIM-B")
            
        Returns:
            Normalized trade print dict or None if invalid
        """
        try:
            # Convert to display symbol
            display_symbol = SymbolMapper.to_display_symbol(hammer_symbol)
            
            # Normalize print data
            normalized = self._normalize_print(raw_print)
            if not normalized:
                self.error_count += 1
                return None
            
            # Add symbol and timestamp
            normalized['symbol'] = display_symbol
            normalized['trade_id'] = normalized.get('trade_id') or f"{display_symbol}_{normalized.get('time', '')}_{self.print_count}"
            
            # Forward to GRPANEngine
            if self.grpan_engine:
                self.grpan_engine.add_trade_print(display_symbol, normalized)
                logger.debug(f"Trade print routed: {display_symbol}, price={normalized.get('price')}, size={normalized.get('size')}")
            else:
                logger.warning("GRPANEngine not available in TradePrintRouter")
            
            self.print_count += 1
            return normalized
            
        except Exception as e:
            logger.error(f"Error routing trade print: {e}", exc_info=True)
            self.error_count += 1
            return None
    
    def _normalize_print(self, raw_print: Any) -> Optional[Dict[str, Any]]:
        """
        Normalize trade print to standard format.
        
        Args:
            raw_print: Raw print (dict or string)
            
        Returns:
            Normalized dict: {'time': str, 'price': float, 'size': float, 'venue': str}
        """
        try:
            if isinstance(raw_print, dict):
                # Dict format from Hammer
                return {
                    'time': raw_print.get('timeStamp') or raw_print.get('time') or datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    'price': float(raw_print.get('price', 0)),
                    'size': float(raw_print.get('size', 0)),
                    'venue': raw_print.get('MMID') or raw_print.get('venue', 'N/A'),
                    'trade_id': raw_print.get('tradeId') or raw_print.get('trade_id')
                }
            elif isinstance(raw_print, str):
                # String format: "time,price,size,venue" or "time,price,size,venue,trade_id"
                parts = raw_print.split(",")
                if len(parts) >= 4:
                    return {
                        'time': parts[0].strip(),
                        'price': float(parts[1]),
                        'size': float(parts[2]),
                        'venue': parts[3].strip(),
                        'trade_id': parts[4].strip() if len(parts) >= 5 else None
                    }
            
            return None
            
        except Exception as e:
            logger.debug(f"Error normalizing print: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get router statistics.
        
        Returns:
            Stats dict with print_count, error_count
        """
        return {
            'print_count': self.print_count,
            'error_count': self.error_count,
            'success_rate': (self.print_count / (self.print_count + self.error_count) * 100) if (self.print_count + self.error_count) > 0 else 0.0
        }

