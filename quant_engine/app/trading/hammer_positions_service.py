"""
Hammer Positions Service
READ-ONLY service to fetch positions from Hammer Pro trading account.
"""

from typing import List, Dict, Any, Optional
from app.core.logger import logger
from app.live.symbol_mapper import SymbolMapper


class HammerPositionsService:
    """
    Service to fetch and normalize positions from Hammer Pro.
    
    READ-ONLY: No order placement, no modifications.
    """
    
    def __init__(self, hammer_client=None):
        """
        Initialize positions service.
        
        Args:
            hammer_client: HammerClient instance (optional, can be set later)
        """
        self.hammer_client = hammer_client
        self.account_key: Optional[str] = None
    
    def set_hammer_client(self, hammer_client, account_key: str):
        """
        Set Hammer client and account key.
        
        Args:
            hammer_client: HammerClient instance
            account_key: Trading account key (e.g., "ALARIC:TOPI002240A7")
        """
        self.hammer_client = hammer_client
        self.account_key = account_key
        logger.info(f"HammerPositionsService initialized with account: {account_key}")
    
    def get_positions(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch positions from Hammer Pro.
        
        Args:
            force_refresh: If True, force refresh from broker instead of cached data
            
        Returns:
            List of normalized position records:
            [
                {
                    'symbol': str,
                    'side': str,  # 'LONG' or 'SHORT'
                    'quantity': float,
                    'avg_price': float,
                    'current_price': float,  # if available
                    'unrealized_pnl': float,  # if available
                    'market_value': float,  # if available
                }
            ]
        """
        if not self.hammer_client:
            logger.warning("Hammer client not set in HammerPositionsService")
            return []
        
        if not self.account_key:
            logger.warning("Account key not set in HammerPositionsService")
            return []
        
        if not self.hammer_client.is_connected():
            logger.warning("Hammer client not connected")
            return []
        
        try:
            # Send getPositions command
            cmd = {
                "cmd": "getPositions",
                "accountKey": self.account_key
            }
            
            if force_refresh:
                cmd["forceRefresh"] = True
            
            logger.debug(f"Fetching positions from Hammer: {self.account_key}")
            response = self.hammer_client.send_command_and_wait(
                cmd,
                wait_for_response=True,
                timeout=10.0
            )
            
            if not response or response.get('success') != 'OK':
                logger.warning(f"Failed to get positions: {response}")
                return []
            
            # Parse positions from response
            # Note: positionsUpdate format varies by broker
            # We'll handle the response structure
            result = response.get('result', {})
            
            # Handle different response formats
            positions_data = []
            
            # Format 1: Direct positions array
            if isinstance(result, list):
                positions_data = result
            # Format 2: Nested in result object
            elif isinstance(result, dict):
                if 'positions' in result:
                    positions_data = result['positions']
                elif 'accountKey' in result:
                    # This might be a positionsUpdate format
                    # Extract positions from the update structure
                    positions_data = result.get('positions', [])
            
            # Normalize positions
            normalized_positions = []
            for pos in positions_data:
                normalized = self._normalize_position(pos)
                if normalized:
                    normalized_positions.append(normalized)
            
            logger.info(f"Fetched {len(normalized_positions)} positions from Hammer")
            return normalized_positions
            
        except Exception as e:
            logger.error(f"Error fetching positions from Hammer: {e}", exc_info=True)
            return []
    
    def _normalize_position(self, pos: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize Hammer position to internal schema.
        
        Args:
            pos: Raw position data from Hammer
            
        Returns:
            Normalized position dict or None if invalid
        """
        try:
            # Extract symbol (field name varies by broker)
            symbol = (
                pos.get('Symbol') or 
                pos.get('symbol') or 
                pos.get('Sym') or
                pos.get('sym')
            )
            
            if not symbol:
                return None
            
            # Normalize symbol from Hammer format to display format
            display_symbol = SymbolMapper.to_display_symbol(symbol)
            
            # Extract quantity (field name varies)
            quantity = (
                pos.get('QTY') or
                pos.get('qty') or
                pos.get('Quantity') or
                pos.get('quantity') or
                pos.get('Position') or
                pos.get('position') or
                0.0
            )
            
            # Determine side (LONG or SHORT)
            # Positive quantity = LONG, Negative = SHORT
            if isinstance(quantity, (int, float)):
                side = 'LONG' if quantity > 0 else 'SHORT'
                quantity = abs(quantity)
            else:
                # Try to get side from Action or other fields
                action = pos.get('Action') or pos.get('action', '').upper()
                if action in ['SELL', 'SHORT']:
                    side = 'SHORT'
                else:
                    side = 'LONG'
                quantity = abs(float(quantity)) if quantity else 0.0
            
            # Extract average price
            avg_price = (
                pos.get('AvgPrice') or
                pos.get('avgPrice') or
                pos.get('AveragePrice') or
                pos.get('averagePrice') or
                pos.get('Basis') or
                pos.get('basis') or
                pos.get('Paid') or
                pos.get('paid') or
                0.0
            )
            avg_price = float(avg_price) if avg_price else 0.0
            
            # Extract current price (if available)
            current_price = (
                pos.get('CurrentPrice') or
                pos.get('currentPrice') or
                pos.get('LastPrice') or
                pos.get('lastPrice') or
                pos.get('Mark') or
                pos.get('mark') or
                None
            )
            current_price = float(current_price) if current_price else None
            
            # Extract unrealized P&L (if available)
            unrealized_pnl = (
                pos.get('UnrealizedPnL') or
                pos.get('unrealizedPnL') or
                pos.get('UnrealizedPnl') or
                pos.get('unrealizedPnl') or
                pos.get('PnL') or
                pos.get('pnl') or
                pos.get('ProfitLoss') or
                pos.get('profitLoss') or
                None
            )
            unrealized_pnl = float(unrealized_pnl) if unrealized_pnl is not None else None
            
            # Calculate market value if we have current price
            market_value = None
            if current_price and quantity:
                market_value = current_price * quantity
            
            return {
                'symbol': display_symbol,  # Use normalized display symbol
                'side': side,
                'quantity': quantity,
                'avg_price': avg_price,
                'current_price': current_price,
                'unrealized_pnl': unrealized_pnl,
                'market_value': market_value
            }
            
        except Exception as e:
            logger.error(f"Error normalizing position: {e}", exc_info=True)
            return None

