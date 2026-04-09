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
        Cancel a single order.
        
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

    # ============================================================================
    # BULK CANCEL OPERATIONS
    # ============================================================================

    def cancel_all_orders(self, reason: str = "manual") -> Dict[str, Any]:
        """
        Cancel ALL open orders (both BUY and SELL).
        
        Args:
            reason: Why the cancel was triggered (e.g., "etf_guard", "manual", "rally", "selloff")
            
        Returns:
            Dict with 'cancelled_count', 'failed_count', 'order_ids', 'errors'
        """
        return self._bulk_cancel(side_filter=None, reason=reason)

    def cancel_all_buys(self, reason: str = "selloff") -> Dict[str, Any]:
        """
        Cancel all BUY orders. Use during selloffs to prevent buying into falling market.
        
        Args:
            reason: Why (e.g., "selloff", "etf_guard_drop")
            
        Returns:
            Dict with cancel results
        """
        return self._bulk_cancel(side_filter="BUY", reason=reason)

    def cancel_all_sells(self, reason: str = "rally") -> Dict[str, Any]:
        """
        Cancel all SELL orders. Use during rallies to prevent selling into rising market.
        
        Args:
            reason: Why (e.g., "rally", "short_squeeze")
            
        Returns:
            Dict with cancel results
        """
        return self._bulk_cancel(side_filter="SELL", reason=reason)

    def cancel_orders_by_tag(self, tag: str, side_filter: str = None, reason: str = "tag_filter") -> Dict[str, Any]:
        """
        Cancel orders matching a specific strategy tag (e.g., 'MM', 'LT', 'PATADD').
        
        Args:
            tag: Strategy tag to filter (e.g., 'MM', 'LT', 'KARBOTU')
            side_filter: Optional 'BUY' or 'SELL' to further filter
            reason: Why
            
        Returns:
            Dict with cancel results
        """
        return self._bulk_cancel(side_filter=side_filter, tag_filter=tag, reason=reason)

    def _bulk_cancel(
        self, 
        side_filter: str = None, 
        tag_filter: str = None,
        reason: str = "manual"
    ) -> Dict[str, Any]:
        """
        Internal bulk cancel implementation.
        
        Args:
            side_filter: None=all, 'BUY'=only buys, 'SELL'=only sells
            tag_filter: Only cancel orders with this strategy tag
            reason: Audit trail reason
            
        Returns:
            Dict with 'cancelled_count', 'failed_count', 'order_ids', 'details'
        """
        result = {
            'cancelled_count': 0,
            'failed_count': 0,
            'order_ids': [],
            'details': [],
            'reason': reason,
            'side_filter': side_filter or 'ALL',
            'tag_filter': tag_filter,
        }
        
        if not self.hammer_client.is_connected():
            logger.error("[BULK_CANCEL] Hammer client not connected")
            result['error'] = "Not connected"
            return result
        
        try:
            # Get open orders from HammerOrdersService
            from app.trading.hammer_orders_service import get_hammer_orders_service
            orders_service = get_hammer_orders_service()
            
            if not orders_service:
                logger.error("[BULK_CANCEL] HammerOrdersService not available")
                result['error'] = "Orders service not available"
                return result
            
            open_orders = orders_service.get_orders(force_refresh=True)
            
            if not open_orders:
                logger.info(f"[BULK_CANCEL] No open orders to cancel (filter={side_filter or 'ALL'})")
                return result
            
            # Filter orders
            targets = []
            for order in open_orders:
                # Side filter
                if side_filter and order.get('side') != side_filter:
                    continue
                # Tag filter
                if tag_filter and order.get('tag') != tag_filter:
                    continue
                targets.append(order)
            
            if not targets:
                filter_desc = f"side={side_filter or 'ALL'}, tag={tag_filter or 'ANY'}"
                logger.info(f"[BULK_CANCEL] No matching orders to cancel ({filter_desc})")
                return result
            
            # Log what we're about to cancel
            target_ids = [t['order_id'] for t in targets]
            filter_desc = side_filter or "ALL"
            logger.warning(
                f"⚡ [BULK_CANCEL] Cancelling {len(targets)} {filter_desc} orders | "
                f"Reason: {reason} | "
                f"Symbols: {', '.join(t['symbol'] for t in targets[:10])}"
                f"{'...' if len(targets) > 10 else ''}"
            )
            
            # Send bulk cancel — Hammer API supports array of orderIDs
            cancel_cmd = {
                "cmd": "tradeCommandCancel",
                "accountKey": self.account_key,
                "orderID": target_ids
            }
            
            if self.hammer_client._send_command(cancel_cmd):
                result['cancelled_count'] = len(target_ids)
                result['order_ids'] = target_ids
                result['details'] = [
                    {
                        'order_id': t['order_id'],
                        'symbol': t['symbol'],
                        'side': t['side'],
                        'qty': t.get('quantity', 0),
                        'price': t.get('price'),
                        'tag': t.get('tag'),
                    }
                    for t in targets
                ]
                
                logger.warning(
                    f"✅ [BULK_CANCEL] Sent cancel for {len(target_ids)} orders | "
                    f"Filter: {filter_desc} | Reason: {reason}"
                )
            else:
                result['failed_count'] = len(target_ids)
                result['error'] = "Failed to send cancel command"
                logger.error(f"[BULK_CANCEL] Failed to send cancel command")
            
        except Exception as e:
            logger.error(f"[BULK_CANCEL] Error: {e}", exc_info=True)
            result['error'] = str(e)
        
        return result

    # ============================================================================
    # ORDER MODIFICATION
    # ============================================================================

    def modify_order_price(self, order_id: str, new_price: float) -> bool:
        """
        Modify the limit price of an existing open order.
        
        Args:
            order_id: The order ID to modify
            new_price: New limit price
            
        Returns:
            True if modification sent successfully
        """
        if not self.hammer_client.is_connected():
            logger.error("Hammer client not connected")
            return False
        
        try:
            modify_cmd = {
                "cmd": "tradeCommandModify",
                "accountKey": self.account_key,
                "order": {
                    "OrderID": order_id,
                    "Legs": [
                        {
                            "LimitPrice": new_price,
                        }
                    ]
                }
            }
            
            if self.hammer_client._send_command(modify_cmd):
                logger.info(f"✏️ [ORDER_MODIFY] Price change sent: OrderID={order_id} → ${new_price}")
                return True
            else:
                logger.error(f"[ORDER_MODIFY] Failed to send modify for OrderID={order_id}")
                return False
        
        except Exception as e:
            logger.error(f"[ORDER_MODIFY] Error: {e}", exc_info=True)
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






