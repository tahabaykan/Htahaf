"""app/live/hammer_execution.py

Hammer Pro execution handler.
Manages order placement, cancellation, and execution tracking.
"""

from typing import Dict, Any, Optional, Callable
from datetime import datetime

from app.core.logger import logger
from app.live.symbol_mapper import SymbolMapper


class HammerExecution:
    """
    Execution handler for Hammer Pro.
    
    Responsibilities:
    - Place orders (tradeCommandNew)
    - Cancel orders (tradeCommandCancel)
    - Track executions (transactionsUpdate)
    - Normalize execution messages
    - Forward to engine callbacks
    """
    
    def __init__(
        self,
        hammer_client,
        account_key: str = "ALARIC:TOPI002240A7",
        execution_callback: Optional[Callable] = None
    ):
        """
        Initialize execution handler.
        
        Args:
            hammer_client: HammerClient instance
            account_key: Trading account key
            execution_callback: Callback for engine.on_execution()
        """
        self.hammer_client = hammer_client
        self.account_key = account_key
        self.execution_callback = execution_callback
        
        # Track pending orders
        self.pending_orders: Dict[str, Dict[str, Any]] = {}
        
        # Set message callback (if not already set by feed)
        if not self.hammer_client.on_message_callback:
            self.hammer_client.on_message_callback = self._handle_message
        else:
            # Chain callbacks
            original_callback = self.hammer_client.on_message_callback
            def chained_callback(data):
                original_callback(data)
                self._handle_message(data)
            self.hammer_client.on_message_callback = chained_callback
    
    def _handle_message(self, data: Dict[str, Any]):
        """Handle incoming Hammer Pro messages"""
        cmd = data.get("cmd", "")
        result = data.get("result", {})
        success = data.get("success", "")
        
        if cmd == "transactionsUpdate":
            self._handle_transactions_update(result)
        elif cmd == "tradeCommandNew":
            if success == "OK":
                logger.info("Order placed successfully")
            else:
                logger.error(f"Order placement failed: {result}")
        elif cmd == "tradeCommandCancel":
            if success == "OK":
                logger.info("Order cancelled successfully")
            else:
                logger.warning(f"Order cancellation failed: {result}")
    
    def _handle_transactions_update(self, result: Dict[str, Any]):
        """Handle transaction updates (executions)"""
        try:
            # Only process changes (not initial snapshot)
            if result.get('setOrChange') != 'change':
                return
            
            transactions = result.get('transactions', [])
            
            for tr in transactions:
                try:
                    status = tr.get('StatusID')
                    is_new = tr.get('New', False)
                    
                    # Only process new fills
                    if status == 'Filled' and is_new:
                        execution = self._normalize_execution(tr)
                        
                        if execution:
                            # Forward to engine
                            if self.execution_callback:
                                try:
                                    self.execution_callback(execution)
                                except Exception as e:
                                    logger.error(f"Error in execution callback: {e}", exc_info=True)
                
                except Exception as e:
                    logger.warning(f"Error processing transaction: {e}")
                    continue
        
        except Exception as e:
            logger.error(f"Error handling transactions update: {e}", exc_info=True)
    
    def _normalize_execution(self, transaction: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Normalize execution message.
        
        Args:
            transaction: Raw transaction from Hammer Pro
            
        Returns:
            Normalized execution message
        """
        try:
            symbol = transaction.get('Symbol')
            if not symbol:
                return None
            
            # Convert to display symbol
            display_symbol = SymbolMapper.to_display_symbol(symbol)
            
            filled_qty = float(transaction.get('FilledQTY', 0))
            if filled_qty <= 0:
                return None
            
            filled_price = float(transaction.get('FilledPrice', transaction.get('LimitPrice', 0)))
            filled_dt = transaction.get('FilledDT', transaction.get('LastTransactionDT'))
            action = transaction.get('Action', '').lower()
            
            execution = {
                "symbol": display_symbol,
                "side": "BUY" if action == "buy" else "SELL",
                "fill_qty": filled_qty,
                "fill_price": filled_price,
                "timestamp": filled_dt,
                "order_id": transaction.get('OrderID', 'N/A'),
                "exec_id": transaction.get('TransactionID', 'N/A')
            }
            
            return execution
        
        except Exception as e:
            logger.error(f"Error normalizing execution: {e}", exc_info=True)
            return None
    
    def place_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        order_type: str = "LIMIT",
        hidden: bool = True
    ) -> bool:
        """
        Place order via Hammer Pro.
        
        Args:
            symbol: Display format symbol
            side: "BUY" or "SELL"
            quantity: Order quantity
            price: Limit price
            order_type: "LIMIT" or "MARKET"
            hidden: If True, use hidden order
            
        Returns:
            True if order sent successfully
        """
        if not self.hammer_client.is_connected():
            logger.error("Hammer client not connected")
            return False
        
        try:
            # Convert to Hammer format
            hammer_symbol = SymbolMapper.to_hammer_symbol(symbol)
            
            # Build order message
            order_message = {
                "cmd": "tradeCommandNew",
                "accountKey": self.account_key,
                "order": {
                    "Legs": [{
                        "Symbol": hammer_symbol,
                        "Action": side.capitalize(),
                        "Quantity": quantity,
                        "OrderType": order_type.capitalize(),
                        "LimitPrice": price,
                        "SpInstructions": "Hidden" if hidden else ""
                    }]
                }
            }
            
            # Send order
            if self.hammer_client._send_command(order_message):
                logger.info(f"Order sent: {side} {quantity} {symbol} @ {price}")
                return True
            else:
                logger.error("Failed to send order")
                return False
        
        except Exception as e:
            logger.error(f"Error placing order: {e}", exc_info=True)
            return False
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if cancellation sent successfully
        """
        if not self.hammer_client.is_connected():
            logger.error("Hammer client not connected")
            return False
        
        try:
            cancel_cmd = {
                "cmd": "tradeCommandCancel",
                "accountKey": self.account_key,
                "orderID": order_id
            }
            
            if self.hammer_client._send_command(cancel_cmd):
                logger.info(f"Cancel order sent: {order_id}")
                return True
            else:
                logger.error("Failed to send cancel order")
                return False
        
        except Exception as e:
            logger.error(f"Error cancelling order: {e}", exc_info=True)
            return False
    
    def get_positions(self) -> list:
        """
        Get current positions.
        
        Returns:
            List of position dictionaries
        """
        try:
            resp = self.hammer_client.send_command_and_wait({
                "cmd": "getPositions",
                "accountKey": self.account_key
            }, wait_for_response=True, timeout=10.0)
            
            if not resp or resp.get('success') != 'OK':
                return []
            
            result = resp.get('result', {})
            positions = result.get('positions', []) if isinstance(result, dict) else (result if isinstance(result, list) else [])
            
            normalized_positions = []
            for pos in positions:
                try:
                    symbol = pos.get('Symbol') or pos.get('sym')
                    if not symbol:
                        continue
                    
                    display_symbol = SymbolMapper.to_display_symbol(symbol)
                    qty = self._extract_qty(pos)
                    
                    if qty != 0:
                        normalized_positions.append({
                            "symbol": display_symbol,
                            "qty": qty,
                            "avg_cost": self._extract_avg_cost(pos)
                        })
                except Exception:
                    continue
            
            return normalized_positions
        
        except Exception as e:
            logger.error(f"Error getting positions: {e}", exc_info=True)
            return []
    
    def _extract_qty(self, pos: Dict[str, Any]) -> float:
        """Extract quantity from position"""
        for key in ("QTY", "Quantity", "Qty", "qty", "Position", "position"):
            val = pos.get(key)
            if val is not None and val != "":
                try:
                    return float(val)
                except (ValueError, TypeError):
                    continue
        
        long_qty = pos.get('LongQty') or pos.get('longQty')
        short_qty = pos.get('ShortQty') or pos.get('shortQty')
        
        if long_qty is not None:
            try:
                return float(long_qty)
            except (ValueError, TypeError):
                pass
        
        if short_qty is not None:
            try:
                return -float(short_qty)
            except (ValueError, TypeError):
                pass
        
        net_qty = pos.get('NetQty') or pos.get('netQty')
        if net_qty is not None:
            try:
                return float(net_qty)
            except (ValueError, TypeError):
                pass
        
        return 0.0
    
    def _extract_avg_cost(self, pos: Dict[str, Any]) -> float:
        """Extract average cost from position"""
        for key in ('Paid', 'paid', 'AvgPrice', 'avg', 'averagePrice', 'AvgCost', 'AverageCost', 'Basis', 'BasisPrice'):
            val = pos.get(key)
            if val is not None and val != "":
                try:
                    return float(val)
                except (ValueError, TypeError):
                    continue
        return 0.0








