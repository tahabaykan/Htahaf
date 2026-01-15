"""
Execution Service

Consumes ev.intents, executes orders via IBKR (stub in Sprint 1),
tracks order lifecycle, publishes ev.orders.
"""

import time
import signal
import uuid
from typing import Dict, Any, Optional
from app.core.logger import logger
from app.core.redis_client import get_redis_client
from app.event_driven.state.event_log import EventLog
from app.event_driven.state.store import StateStore
from app.event_driven.contracts.events import IntentEvent, OrderEvent, BaseEvent, OrderClassification
from app.event_driven.execution.liquidity_guard import LiquidityGuard


class ExecutionService:
    """Execution Service - the ONLY component that talks to IBKR"""
    
    def __init__(self, worker_name: str = "execution_service"):
        self.worker_name = worker_name
        self.running = False
        self.event_log: Optional[EventLog] = None
        self.state_store: Optional[StateStore] = None
        
        # Track open orders in Redis (by symbol, side, intent_id, status)
        self.open_orders_key = "orders:open"
        self.order_registry_key = "orders:registry"  # order_id -> order data
        
        # Consumer group name
        self.consumer_group = "execution_service"
        self.consumer_name = f"{worker_name}_{int(time.time())}"
        
        # LiquidityGuard
        self.liquidity_guard = LiquidityGuard()
        
        # Mock avg_adv lookup (in production, fetch from market data)
        self.mock_avg_adv = {
            "AAPL": 50000000,  # 50M shares/day
            "MSFT": 30000000,
            "GOOGL": 20000000,
            "TSLA": 100000000,
        }
    
    def connect(self):
        """Connect to Redis and initialize consumer groups"""
        try:
            redis_client = get_redis_client().sync
            if not redis_client:
                raise RuntimeError("Redis client not available")
            
            self.event_log = EventLog(redis_client=redis_client)
            self.state_store = StateStore(redis_client=redis_client)
            
            # Create consumer group for intents stream
            try:
                self.event_log.create_consumer_group("intents", self.consumer_group)
            except Exception as e:
                logger.warning(f"⚠️ [{self.worker_name}] Consumer group creation warning: {e}")
            
            logger.info(f"✅ [{self.worker_name}] Connected to Redis")
            return True
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Failed to connect: {e}", exc_info=True)
            return False
    
    def _get_intent_id(self, intent_data: Dict[str, Any]) -> str:
        """Extract intent ID from intent data (for idempotency)"""
        # Use event_id as intent_id for idempotency
        return intent_data.get("event_id", str(uuid.uuid4()))
    
    def _check_idempotency(self, intent_id: str) -> Optional[str]:
        """Check if intent was already processed (returns existing order_id if found)"""
        try:
            # Check Redis for existing order with this intent_id
            registry_data = self.state_store.get_state("orders_registry")
            if registry_data:
                for order_id, order_data_str in registry_data.items():
                    import json
                    order_data = json.loads(order_data_str) if isinstance(order_data_str, str) else order_data_str
                    if order_data.get("intent_id") == intent_id:
                        return order_id
            return None
        except Exception as e:
            logger.warning(f"⚠️ [{self.worker_name}] Error checking idempotency: {e}")
            return None
    
    def _register_order(self, order_id: str, order_data: Dict[str, Any]):
        """Register order in Redis"""
        try:
            import json
            # Store in registry
            self.state_store.update_state("orders_registry", {
                order_id: json.dumps(order_data)
            })
            
            # Add to open orders set (by symbol:side)
            symbol = order_data["symbol"]
            side = order_data["action"]  # BUY or SELL
            open_key = f"{self.open_orders_key}:{symbol}:{side}"
            self.state_store.redis.sadd(open_key, order_id)
            
            logger.debug(f"✅ [{self.worker_name}] Registered order: {order_id}")
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error registering order: {e}", exc_info=True)
    
    def _unregister_order(self, order_id: str, order_data: Dict[str, Any]):
        """Unregister order from Redis (when filled/cancelled)"""
        try:
            symbol = order_data["symbol"]
            side = order_data["action"]
            open_key = f"{self.open_orders_key}:{symbol}:{side}"
            self.state_store.redis.srem(open_key, order_id)
            
            # Remove from registry (or mark as closed)
            import json
            order_data["status"] = "CLOSED"
            self.state_store.update_state("orders_registry", {
                order_id: json.dumps(order_data)
            })
            
            logger.debug(f"✅ [{self.worker_name}] Unregistered order: {order_id}")
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error unregistering order: {e}", exc_info=True)
    
    def process_intent(self, intent_data: Dict[str, str]):
        """Process intent and execute order (deterministic simulator)"""
        try:
            # Parse intent event
            import json
            data_str = intent_data.get("data", "{}")
            if isinstance(data_str, str):
                data = json.loads(data_str)
            else:
                data = data_str
            
            # Get intent_id for idempotency
            intent_id = intent_data.get("event_id", str(uuid.uuid4()))
            
            # Check idempotency
            existing_order_id = self._check_idempotency(intent_id)
            if existing_order_id:
                logger.info(
                    f"⏭️ [{self.worker_name}] Intent already processed: "
                    f"intent_id={intent_id}, existing_order={existing_order_id}"
                )
                return  # Skip duplicate
            
            intent_type = data.get("intent_type", "UNKNOWN")
            symbol = data.get("symbol", "UNKNOWN")
            action = data.get("action", "UNKNOWN")
            quantity = data.get("quantity", 0)
            reason = data.get("reason", "")
            limit_price = data.get("limit_price")
            
            # Extract classification (MUST be present)
            classification = data.get("classification", "")
            bucket = data.get("bucket", "LT")
            effect = data.get("effect", "DECREASE")
            direction = data.get("dir", "LONG")
            risk_delta_notional = data.get("risk_delta_notional", 0.0)
            risk_delta_gross_pct = data.get("risk_delta_gross_pct", 0.0)
            position_context = data.get("position_context_at_intent", {})
            
            if not classification:
                logger.error(f"❌ [{self.worker_name}] Intent missing classification: {intent_id}")
                return
            
            logger.info(
                f"📥 [{self.worker_name}] Received intent: "
                f"{intent_type} {action} {quantity} {symbol} [{classification}] - {reason}"
            )
            
            # Apply LiquidityGuard constraints
            avg_adv = self.mock_avg_adv.get(symbol, 1000000)  # Default: 1M shares/day
            
            # Get minutes_to_close from session state (stub for now)
            minutes_to_close = None  # TODO: Get from session state
            
            # Validate and adjust quantity
            is_valid, adjusted_qty, adjustment_info = self.liquidity_guard.validate_order(
                symbol=symbol,
                classification=classification,
                desired_qty=quantity,
                avg_adv=avg_adv,
                bucket=bucket,
                minutes_to_close=minutes_to_close,
                intent_type=intent_type
            )
            
            if not is_valid:
                logger.warning(
                    f"🛑 [{self.worker_name}] Order deferred by LiquidityGuard: "
                    f"{symbol} qty={quantity} [{classification}] - {adjustment_info.get('reason', '')}"
                )
                return  # Defer order
            
            if adjusted_qty != quantity:
                logger.info(
                    f"✂️ [{self.worker_name}] Quantity adjusted by LiquidityGuard: "
                    f"{symbol} {quantity} → {adjusted_qty} [{classification}]"
                )
                quantity = adjusted_qty
            
            # Generate order ID
            order_id = f"ORD_{uuid.uuid4().hex[:8]}"
            
            # Create order record with classification
            order_data = {
                "order_id": order_id,
                "intent_id": intent_id,
                "symbol": symbol,
                "action": action,
                "quantity": quantity,
                "limit_price": limit_price,
                "status": "ACCEPTED",
                "intent_type": intent_type,
                "classification": classification,
                "bucket": bucket,
                "effect": effect,
                "direction": direction,
                "risk_delta_notional": risk_delta_notional,
                "risk_delta_gross_pct": risk_delta_gross_pct,
                "position_context_at_intent": position_context,
                "created_at": time.time(),
                "filled_quantity": 0,
                "avg_fill_price": None,
            }
            
            # Register order
            self._register_order(order_id, order_data)
            
            # Publish ACCEPTED event (with classification preserved)
            account_id = position_context.get("account_id", "HAMMER")
            order_event = OrderEvent.create(
                order_id=order_id,
                symbol=symbol,
                action="ACCEPTED",
                quantity=quantity,
                order_type="LIMIT" if limit_price else "MARKET",
                classification=classification,
                bucket=bucket,
                effect=effect,
                dir=direction,
                risk_delta_notional=risk_delta_notional,
                risk_delta_gross_pct=risk_delta_gross_pct,
                position_context_at_intent=position_context,
                limit_price=limit_price,
                status="ACCEPTED",
                intent_id=intent_id,
                order_action=action,  # BUY or SELL
                account_id=account_id,
            )
            self.event_log.publish("orders", order_event)
            
            # Publish WORKING event (order is now working)
            working_event = OrderEvent.create(
                order_id=order_id,
                symbol=symbol,
                action="WORKING",
                quantity=quantity,
                order_type="LIMIT" if limit_price else "MARKET",
                classification=classification,
                bucket=bucket,
                effect=effect,
                dir=direction,
                risk_delta_notional=risk_delta_notional,
                risk_delta_gross_pct=risk_delta_gross_pct,
                position_context_at_intent=position_context,
                limit_price=limit_price,
                status="WORKING",
                intent_id=intent_id,
                order_action=action,  # BUY or SELL
                account_id=account_id,
            )
            self.event_log.publish("orders", working_event)
            
            logger.info(f"✅ [{self.worker_name}] Order accepted and working: {order_id}")
            
            # Simulate fill (deterministic rules)
            self._simulate_fill_deterministic(order_id, order_data)
        
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error processing intent: {e}", exc_info=True)
    
    def _simulate_fill_deterministic(self, order_id: str, order_data: Dict[str, Any]):
        """Simulate order fill with deterministic rules"""
        try:
            import json
            
            # Deterministic fill rules:
            # - HARD_DERISK: immediate fill (100% probability)
            # - SOFT_DERISK: high probability (90%)
            # - Other: medium probability (50%)
            intent_type = order_data.get("intent_type", "")
            fill_probability = {
                "HARD_DERISK": 1.0,
                "SOFT_DERISK": 0.9,
            }.get(intent_type, 0.5)
            
            import random
            # Use deterministic seed based on order_id for reproducibility
            seed = hash(order_id) % (2**32)
            random.seed(seed)
            
            if random.random() < fill_probability:
                # Fill the order
                filled_quantity = order_data["quantity"]
                limit_price = order_data.get("limit_price")
                
                # For limit orders, use limit price; for market, use mock price
                if limit_price:
                    avg_fill_price = limit_price
                else:
                    # Mock market price (in real system, use current market price)
                    avg_fill_price = 100.0
                
                # Update order data
                order_data["status"] = "FILLED"
                order_data["filled_quantity"] = filled_quantity
                order_data["avg_fill_price"] = avg_fill_price
                order_data["filled_at"] = time.time()
                
                # Update registry
                self.state_store.update_state("orders_registry", {
                    order_id: json.dumps(order_data)
                })
                
                # Publish PARTIAL_FILL or FILLED event
                # Preserve classification in fill events
                classification = order_data.get("classification", "")
                bucket = order_data.get("bucket", "LT")
                effect = order_data.get("effect", "DECREASE")
                direction = order_data.get("direction", "LONG")
                risk_delta_notional = order_data.get("risk_delta_notional", 0.0)
                risk_delta_gross_pct = order_data.get("risk_delta_gross_pct", 0.0)
                position_context = order_data.get("position_context_at_intent", {})
                intent_id = order_data.get("intent_id", "")
                order_action = order_data.get("action", "")  # BUY or SELL
                account_id = position_context.get("account_id", "HAMMER")
                
                if filled_quantity < order_data["quantity"]:
                    fill_event = OrderEvent.create(
                        order_id=order_id,
                        symbol=order_data["symbol"],
                        action="PARTIAL_FILL",
                        quantity=order_data["quantity"],
                        order_type="LIMIT" if limit_price else "MARKET",
                        classification=classification,
                        bucket=bucket,
                        effect=effect,
                        dir=direction,
                        risk_delta_notional=risk_delta_notional,
                        risk_delta_gross_pct=risk_delta_gross_pct,
                        position_context_at_intent=position_context,
                        limit_price=limit_price,
                        filled_quantity=filled_quantity,
                        avg_fill_price=avg_fill_price,
                        status="PARTIAL_FILL",
                        intent_id=intent_id,
                        order_action=order_action,
                        account_id=account_id,
                    )
                else:
                    fill_event = OrderEvent.create(
                        order_id=order_id,
                        symbol=order_data["symbol"],
                        action="FILLED",
                        quantity=order_data["quantity"],
                        order_type="LIMIT" if limit_price else "MARKET",
                        classification=classification,
                        bucket=bucket,
                        effect=effect,
                        dir=direction,
                        risk_delta_notional=risk_delta_notional,
                        risk_delta_gross_pct=risk_delta_gross_pct,
                        position_context_at_intent=position_context,
                        limit_price=limit_price,
                        filled_quantity=filled_quantity,
                        avg_fill_price=avg_fill_price,
                        status="FILLED",
                        intent_id=intent_id,
                        order_action=order_action,
                        account_id=account_id,
                    )
                
                self.event_log.publish("orders", fill_event)
                
                # Unregister order
                self._unregister_order(order_id, order_data)
                
                logger.info(
                    f"✅ [{self.worker_name}] Simulated fill: "
                    f"order_id={order_id}, filled={filled_quantity} @ {avg_fill_price}"
                )
            else:
                # Order not filled (simulate timeout or cancellation)
                logger.debug(f"⏳ [{self.worker_name}] Order not filled (probability): {order_id}")
        
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error simulating fill: {e}", exc_info=True)
    
    def cancel_risk_increasing_open_orders(self, reason: str = "Hard cap reached"):
        """Cancel all risk-increasing open orders (*_INCREASE)"""
        try:
            import json
            registry_data = self.state_store.get_state("orders_registry")
            if not registry_data:
                return 0
            
            canceled_count = 0
            for order_id, order_data_str in registry_data.items():
                try:
                    order_data = json.loads(order_data_str) if isinstance(order_data_str, str) else order_data_str
                    status = order_data.get("status", "")
                    classification = order_data.get("classification", "")
                    
                    # Only cancel open orders that are risk-increasing
                    if status in ["ACCEPTED", "WORKING", "PARTIAL_FILL"]:
                        # Check if classification ends with _INCREASE
                        if classification.endswith("_INCREASE"):
                            if self.cancel_order(order_id, reason):
                                canceled_count += 1
                                logger.info(
                                    f"🚨 [{self.worker_name}] Canceled risk-increasing order: "
                                    f"{order_id} [{classification}]"
                                )
                except Exception as e:
                    logger.warning(f"⚠️ [{self.worker_name}] Error processing order {order_id}: {e}")
                    continue
            
            logger.info(f"✅ [{self.worker_name}] Canceled {canceled_count} risk-increasing orders")
            return canceled_count
        
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error canceling risk-increasing orders: {e}", exc_info=True)
            return 0
    
    def cancel_order(self, order_id: str, reason: str = "User request"):
        """Cancel an open order"""
        try:
            import json
            registry_data = self.state_store.get_state("orders_registry")
            if not registry_data:
                logger.warning(f"⚠️ [{self.worker_name}] Order not found: {order_id}")
                return False
            
            order_data_str = registry_data.get(order_id)
            if not order_data_str:
                logger.warning(f"⚠️ [{self.worker_name}] Order not found: {order_id}")
                return False
            
            order_data = json.loads(order_data_str) if isinstance(order_data_str, str) else order_data_str
            
            if order_data.get("status") in ["FILLED", "CANCELED", "REJECTED"]:
                logger.warning(f"⚠️ [{self.worker_name}] Order already closed: {order_id}")
                return False
            
            # Update status
            order_data["status"] = "CANCELED"
            order_data["canceled_at"] = time.time()
            order_data["cancel_reason"] = reason
            
            # Update registry
            self.state_store.update_state("orders_registry", {
                order_id: json.dumps(order_data)
            })
            
            # Preserve classification in cancel event
            classification = order_data.get("classification", "")
            bucket = order_data.get("bucket", "LT")
            effect = order_data.get("effect", "DECREASE")
            direction = order_data.get("direction", "LONG")
            risk_delta_notional = order_data.get("risk_delta_notional", 0.0)
            risk_delta_gross_pct = order_data.get("risk_delta_gross_pct", 0.0)
            position_context = order_data.get("position_context_at_intent", {})
            intent_id = order_data.get("intent_id", "")
            
            # Publish CANCELED event
            cancel_event = OrderEvent.create(
                order_id=order_id,
                symbol=order_data["symbol"],
                action="CANCELED",
                quantity=order_data["quantity"],
                order_type="LIMIT" if order_data.get("limit_price") else "MARKET",
                classification=classification,
                bucket=bucket,
                effect=effect,
                dir=direction,
                risk_delta_notional=risk_delta_notional,
                risk_delta_gross_pct=risk_delta_gross_pct,
                position_context_at_intent=position_context,
                limit_price=order_data.get("limit_price"),
                status="CANCELED",
                intent_id=intent_id,
            )
            self.event_log.publish("orders", cancel_event)
            
            # Unregister
            self._unregister_order(order_id, order_data)
            
            logger.info(f"✅ [{self.worker_name}] Order canceled: {order_id}")
            return True
        
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error canceling order: {e}", exc_info=True)
            return False
    
    def run(self):
        """Main service loop"""
        try:
            logger.info(f"🚀 [{self.worker_name}] Starting...")
            
            if not self.connect():
                logger.error(f"❌ [{self.worker_name}] Cannot start: connection failed")
                return
            
            self.running = True
            logger.info(f"✅ [{self.worker_name}] Started (consumer: {self.consumer_name})")
            logger.info(f"💡 [{self.worker_name}] STUB MODE: Logging actions, not executing real orders")
            
            # Main loop - read from intents and exposure streams
            while self.running:
                try:
                    # Read intents
                    messages = self.event_log.read(
                        "intents", self.consumer_group, self.consumer_name,
                        count=10, block=1000
                    )
                    
                    for msg in messages:
                        # msg["data"] is already a dict from Redis Stream
                        # Extract event_id and data field
                        event_id = msg["data"].get("event_id", "")
                        data_str = msg["data"].get("data", "{}")
                        # Create intent_data dict with event_id
                        intent_data = {
                            "event_id": event_id,
                            "data": data_str
                        }
                        self.process_intent(intent_data)
                        self.event_log.ack("intents", self.consumer_group, msg["message_id"])
                    
                    # Check exposure for hard cap (cancel risk-increasing orders)
                    exposure_messages = self.event_log.read(
                        "exposure", self.consumer_group, self.consumer_name,
                        count=1, block=0  # Non-blocking check
                    )
                    
                    for msg in exposure_messages:
                        import json
                        data_str = msg["data"].get("data", "{}")
                        exposure_data = json.loads(data_str) if isinstance(data_str, str) else data_str
                        gross_exposure_pct = exposure_data.get("gross_exposure_pct", 0.0)
                        
                        # If hard cap reached, cancel risk-increasing orders
                        if gross_exposure_pct >= 130.0:
                            self.cancel_risk_increasing_open_orders("Hard cap reached")
                        
                        self.event_log.ack("exposure", self.consumer_group, msg["message_id"])
                
                except Exception as e:
                    logger.error(f"❌ [{self.worker_name}] Error in main loop: {e}", exc_info=True)
                    time.sleep(1)
        
        except KeyboardInterrupt:
            logger.info(f"🛑 [{self.worker_name}] Stopped by user")
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error: {e}", exc_info=True)
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup resources"""
        self.running = False
        logger.info(f"✅ [{self.worker_name}] Cleanup completed")


def main():
    """Main entry point"""
    service = ExecutionService()
    
    def signal_handler(sig, frame):
        logger.info(f"🛑 [{service.worker_name}] Received SIGINT, shutting down...")
        service.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    service.run()


if __name__ == "__main__":
    main()

