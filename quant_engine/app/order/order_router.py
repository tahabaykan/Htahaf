"""app/order/order_router.py

Order router - consumes orders from Redis stream and executes them via IBKR.
Handles order execution, status tracking, and error handling.
"""

import json
import time
from typing import Optional, Dict, Any

# Lazy import ib_insync to avoid event loop issues
# PHASE 10.1: Do NOT apply nest_asyncio globally - it breaks uvicorn
try:
    from ib_insync import IB, Stock, MarketOrder, LimitOrder
    IB_AVAILABLE = True
except (ImportError, RuntimeError) as e:
    IB_AVAILABLE = False
    # Create dummy classes for type hints
    IB = None
    Stock = None
    MarketOrder = None
    LimitOrder = None

from app.core.logger import logger
from app.core.event_bus import EventBus
from app.order.order_message import OrderMessage
from app.config.settings import settings


class OrderRouter:
    """Routes orders from Redis stream to IBKR"""
    
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None, client_id: Optional[int] = None):
        """
        Initialize order router.
        
        Args:
            host: IBKR host (default: from settings)
            port: IBKR port (default: from settings)
            client_id: IBKR client ID (default: from settings)
        """
        if not IB_AVAILABLE:
            raise ImportError("ib_insync not available. Install with: pip install ib_insync")
        
        self.ib = IB()
        self.host = host or settings.IBKR_HOST
        self.port = port or settings.IBKR_PORT
        self.client_id = client_id or settings.IBKR_CLIENT_ID
        self.connected = False
        self.running = False
        self.orders_stream = "orders"
        self.last_id = "0-0"
        self.order_count = 0
        self.error_count = 0
    
    def connect(self) -> bool:
        """
        Connect to IBKR TWS/Gateway.
        
        Returns:
            True if connected successfully
        """
        try:
            logger.info(f"Connecting to IBKR ({self.host}:{self.port}, Client ID: {self.client_id})")
            self.ib.connect(self.host, self.port, clientId=self.client_id, timeout=15)
            
            if self.ib.isConnected():
                self.connected = True
                logger.info("✅ Connected to IBKR successfully")
                
                # Set up order status callbacks
                self.ib.orderStatusEvent += self._on_order_status
                self.ib.executionEvent += self._on_execution
                
                return True
            else:
                logger.error("❌ IBKR connection failed")
                return False
        except Exception as e:
            logger.error(f"IBKR connection error: {e}")
            self.connected = False
            return False
    
    def disconnect(self):
        """Disconnect from IBKR"""
        try:
            if self.connected:
                self.ib.disconnect()
                self.connected = False
                logger.info("Disconnected from IBKR")
        except Exception as e:
            logger.error(f"Error disconnecting from IBKR: {e}")
    
    def _on_order_status(self, trade):
        """Order status callback - captures order status updates"""
        try:
            status = trade.orderStatus.status
            order_id = trade.order.orderId
            symbol = trade.contract.symbol
            
            logger.info(f"Order status: {symbol} OrderID={order_id} Status={status}")
            
            # Publish order status event
            EventBus.publish("order_status", {
                "order_id": order_id,
                "symbol": symbol,
                "status": status,
                "filled": float(trade.orderStatus.filled),
                "remaining": float(trade.orderStatus.remaining),
                "avg_fill_price": float(trade.orderStatus.avgFillPrice or 0),
                "timestamp": int(time.time() * 1000)
            })
            
            # If order is filled or partially filled, create execution message
            if status in ['Filled', 'PartiallyFilled']:
                self._publish_execution_from_trade(trade)
        except Exception as e:
            logger.error(f"Error in order status callback: {e}", exc_info=True)
    
    def _on_execution(self, trade, fill):
        """
        Execution callback - captures individual fills.
        
        Creates normalized execution message and publishes to Redis.
        
        Normalized message format:
        {
            "symbol": str,
            "side": "BUY" | "SELL",
            "fill_qty": float,
            "fill_price": float,
            "order_id": int,
            "exec_id": str,
            "timestamp": int (ms)
        }
        """
        try:
            symbol = trade.contract.symbol
            exec_price = float(fill.execution.price)
            exec_qty = float(fill.execution.shares)
            exec_id = fill.execution.execId
            order_id = trade.order.orderId
            side = trade.order.action.upper()  # BUY or SELL
            
            logger.info(f"Execution: {symbol} {exec_qty} @ {exec_price} (ExecID: {exec_id})")
            
            # Create normalized execution message (EXPORT format)
            exec_msg = {
                "symbol": symbol,
                "side": side,
                "fill_qty": exec_qty,
                "fill_price": exec_price,
                "order_id": order_id,
                "exec_id": exec_id,
                "timestamp": int(time.time() * 1000),
                # Additional fields for compatibility
                "qty": exec_qty,  # Alias for fill_qty
                "price": exec_price,  # Alias for fill_price
                "remaining": float(trade.orderStatus.remaining),
                "avg_fill_price": float(trade.orderStatus.avgFillPrice or exec_price)
            }
            
            # Publish to Redis stream (durable)
            EventBus.stream_add("executions", exec_msg)
            
            # Also publish to pub/sub for real-time updates
            EventBus.publish("executions", exec_msg)
            
        except Exception as e:
            logger.error(f"Error in execution callback: {e}", exc_info=True)
    
    def _publish_execution_from_trade(self, trade):
        """Publish execution message from trade object (for order status updates)"""
        try:
            symbol = trade.contract.symbol
            order_id = trade.order.orderId
            status = trade.orderStatus.status
            
            # Only publish if there's a fill
            if trade.orderStatus.filled > 0:
                exec_msg = {
                    "symbol": symbol,
                    "qty": float(trade.orderStatus.filled),
                    "price": float(trade.orderStatus.avgFillPrice or 0),
                    "side": trade.order.action.upper(),
                    "timestamp": int(time.time() * 1000),
                    "order_id": order_id,
                    "exec_id": f"status_{order_id}",
                    "remaining": float(trade.orderStatus.remaining),
                    "avg_fill_price": float(trade.orderStatus.avgFillPrice or 0)
                }
                
                # Publish to stream
                EventBus.stream_add("executions", exec_msg)
                
        except Exception as e:
            logger.error(f"Error publishing execution from trade: {e}", exc_info=True)
    
    def start(self):
        """Start order router loop"""
        if not self.connected:
            logger.error("Not connected to IBKR. Call connect() first.")
            return
        
        logger.info("🚀 Order Router started")
        self.running = True
        
        try:
            while self.running:
                try:
                    # Read from orders stream
                    msg = EventBus.stream_read(
                        self.orders_stream,
                        last_id=self.last_id,
                        block=1000,
                        count=1
                    )
                    
                    if msg is None:
                        continue
                    
                    # Update last_id
                    self.last_id = msg["id"]
                    
                    # Parse message
                    try:
                        data = msg["data"]
                        
                        # Decode bytes if needed
                        if isinstance(data, dict):
                            # Already decoded
                            order_data = data
                        else:
                            # Try to decode
                            if isinstance(data, bytes):
                                order_data = json.loads(data.decode())
                            else:
                                order_data = json.loads(data)
                        
                        # Create order message
                        order_msg = OrderMessage(**order_data)
                        order_msg.validate()
                        
                        # Execute order
                        trade = self._execute(order_msg)
                        
                        if trade:
                            self.order_count += 1
                            logger.info(
                                f"Order executed: {order_msg.symbol} {order_msg.side} "
                                f"{order_msg.qty} (OrderID: {trade.order.orderId})"
                            )
                        
                        # Note: Stream ACK not needed for simple XREAD (not consumer groups)
                        # If using consumer groups, uncomment:
                        # EventBus.stream_ack(self.orders_stream, "router_group", msg["id"])
                    
                    except Exception as e:
                        self.error_count += 1
                        logger.error(f"Order router error: {e}", exc_info=True)
                        time.sleep(0.2)
                
                except KeyboardInterrupt:
                    logger.info("Keyboard interrupt received")
                    break
                except Exception as e:
                    self.error_count += 1
                    logger.error(f"Error in router loop: {e}", exc_info=True)
                    time.sleep(1)
        
        finally:
            self.stop()
    
    def _execute(self, msg: OrderMessage):
        """
        Execute order via IBKR.
        
        Args:
            msg: OrderMessage instance
            
        Returns:
            Trade object or None
        """
        try:
            symbol = msg.symbol
            side = msg.side.upper()
            qty = msg.qty
            
            # Create contract
            contract = Stock(symbol, "SMART", "USD")
            
            logger.info(f"[ORDER] {side} {qty} {symbol} ({msg.order_type})")
            
            # Create order
            if msg.order_type.upper() == "MKT":
                order = MarketOrder(side, qty)
            elif msg.order_type.upper() == "LMT":
                if msg.limit_price is None:
                    raise ValueError("limit_price required for LMT orders")
                order = LimitOrder(side, qty, msg.limit_price, tif='DAY')
            else:
                raise ValueError(f"Unsupported order type: {msg.order_type}")
            
            # Place order
            trade = self.ib.placeOrder(contract, order)
            
            # Wait a bit for status update
            self.ib.sleep(0.1)
            
            logger.info(f"[IBKR] Status={trade.orderStatus.status} OrderID={trade.order.orderId}")
            
            return trade
        
        except Exception as e:
            logger.error(f"Error executing order: {e}", exc_info=True)
            return None
    
    def stop(self):
        """Stop order router"""
        logger.info("Stopping Order Router...")
        self.running = False
        self.disconnect()
        logger.info(
            f"Order Router stopped. Orders: {self.order_count}, Errors: {self.error_count}"
        )

