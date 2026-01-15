"""app/ibkr/ibkr_sync.py

IBKR synchronization - fetches positions, orders, and account data from IBKR.
Used for system startup and position reconciliation.
"""

from typing import Dict, List, Any, Optional

from app.ibkr.ibkr_client import ibkr_client
from app.core.logger import logger


class IBKRSync:
    """IBKR synchronization utilities"""
    
    def __init__(self):
        self.client = ibkr_client
    
    def fetch_open_positions(self) -> List[Dict[str, Any]]:
        """
        Fetch all open positions from IBKR.
        
        Returns:
            List of position dicts
        """
        try:
            if not self.client.is_connected():
                logger.warning("IBKR not connected, cannot fetch positions")
                return []
            
            positions = self.client.ib.positions()
            result = []
            
            for pos in positions:
                position_data = {
                    'symbol': pos.contract.symbol,
                    'qty': float(pos.position),
                    'avg_price': float(getattr(pos, 'averageCost', 0)),
                    'account': pos.account,
                    'market_value': float(getattr(pos, 'marketValue', 0)),
                    'unrealized_pnl': float(getattr(pos, 'unrealizedPNL', 0)),
                    'realized_pnl': float(getattr(pos, 'realizedPNL', 0))
                }
                result.append(position_data)
            
            logger.info(f"Fetched {len(result)} open positions from IBKR")
            return result
            
        except Exception as e:
            logger.error(f"Error fetching positions: {e}", exc_info=True)
            return []
    
    def fetch_open_orders(self) -> List[Dict[str, Any]]:
        """
        Fetch all open orders from IBKR.
        
        Returns:
            List of order dicts
        """
        try:
            if not self.client.is_connected():
                logger.warning("IBKR not connected, cannot fetch orders")
                return []
            
            open_orders = self.client.ib.reqAllOpenOrders()
            result = []
            
            for order in open_orders:
                order_data = {
                    'order_id': order.order.orderId,
                    'symbol': order.contract.symbol,
                    'action': order.order.action,
                    'quantity': float(order.order.totalQuantity),
                    'order_type': order.order.orderType,
                    'limit_price': float(order.order.lmtPrice) if order.order.lmtPrice else None,
                    'status': order.orderStatus.status,
                    'filled': float(order.orderStatus.filled),
                    'remaining': float(order.orderStatus.remaining),
                    'avg_fill_price': float(order.orderStatus.avgFillPrice) if order.orderStatus.avgFillPrice else None
                }
                result.append(order_data)
            
            logger.info(f"Fetched {len(result)} open orders from IBKR")
            return result
            
        except Exception as e:
            logger.error(f"Error fetching orders: {e}", exc_info=True)
            return []
    
    def fetch_account_summary(self, account: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetch account summary from IBKR.
        
        Args:
            account: Account ID (None = all accounts)
            
        Returns:
            Account summary dict
        """
        try:
            if not self.client.is_connected():
                logger.warning("IBKR not connected, cannot fetch account summary")
                return {}
            
            # Get account values
            account_values = self.client.ib.accountValues()
            
            # Filter by account if specified
            if account:
                account_values = [av for av in account_values if av.account == account]
            
            # Build summary
            summary = {
                'accounts': list(set([av.account for av in account_values])),
                'values': {}
            }
            
            # Extract key values
            for av in account_values:
                key = av.tag
                if key not in summary['values']:
                    summary['values'][key] = {}
                summary['values'][key][av.account] = av.value
            
            # Common fields
            common_fields = [
                'NetLiquidation',
                'TotalCashValue',
                'BuyingPower',
                'GrossPositionValue',
                'AvailableFunds',
                'ExcessLiquidity'
            ]
            
            summary['common'] = {}
            for field in common_fields:
                for av in account_values:
                    if av.tag == field:
                        if field not in summary['common']:
                            summary['common'][field] = {}
                        summary['common'][field][av.account] = av.value
            
            logger.info(f"Fetched account summary for {len(summary['accounts'])} account(s)")
            return summary
            
        except Exception as e:
            logger.error(f"Error fetching account summary: {e}", exc_info=True)
            return {}
    
    def sync_positions_to_manager(self, position_manager):
        """
        Sync IBKR positions to position manager.
        
        Args:
            position_manager: PositionManager instance
        """
        try:
            positions = self.fetch_open_positions()
            
            for pos in positions:
                symbol = pos['symbol']
                qty = pos['qty']
                avg_price = pos['avg_price']
                
                if qty != 0:
                    # Update position (qty is already signed: positive = long, negative = short)
                    position_manager.update_position(symbol, qty, avg_price)
                    logger.info(f"Synced position: {symbol} = {qty} @ {avg_price:.2f}")
            
            logger.info(f"Synced {len(positions)} positions to position manager")
            
        except Exception as e:
            logger.error(f"Error syncing positions: {e}", exc_info=True)


# Global sync instance
ibkr_sync = IBKRSync()








