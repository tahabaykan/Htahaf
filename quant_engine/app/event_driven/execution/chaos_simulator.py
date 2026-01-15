"""
Execution Chaos Simulator

Simulates adversarial broker behavior:
- Out-of-order events
- Partial fills + replace
- Cancel rejection
- Latency simulation
- Duplicate events
"""

import time
import random
import uuid
from typing import Dict, Any, Optional, List, Tuple
from collections import deque
from app.core.logger import logger
from app.event_driven.execution.service import ExecutionService


class ChaosExecutionSimulator(ExecutionService):
    """Execution Service with chaos mode for adversarial testing"""
    
    def __init__(
        self,
        worker_name: str = "chaos_execution_service",
        chaos_config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(worker_name=worker_name)
        
        # Chaos configuration
        self.chaos_config = chaos_config or {}
        self.chaos_enabled = self.chaos_config.get("enabled", False)
        self.out_of_order_enabled = self.chaos_config.get("out_of_order", False)
        self.latency_enabled = self.chaos_config.get("latency", False)
        self.duplicate_enabled = self.chaos_config.get("duplicate", False)
        self.partial_fill_enabled = self.chaos_config.get("partial_fill", False)
        self.cancel_rejection_enabled = self.chaos_config.get("cancel_rejection", False)
        
        # Latency parameters
        self.latency_min = self.chaos_config.get("latency_min_seconds", 1.0)
        self.latency_max = self.chaos_config.get("latency_max_seconds", 5.0)
        
        # Duplicate probability
        self.duplicate_probability = self.chaos_config.get("duplicate_probability", 0.1)
        
        # Partial fill parameters
        self.partial_fill_probability = self.chaos_config.get("partial_fill_probability", 0.3)
        self.partial_fill_min_pct = self.chaos_config.get("partial_fill_min_pct", 0.1)
        self.partial_fill_max_pct = self.chaos_config.get("partial_fill_max_pct", 0.7)
        
        # Cancel rejection probability
        self.cancel_rejection_probability = self.chaos_config.get("cancel_rejection_probability", 0.2)
        
        # Event queues for out-of-order simulation
        self.event_queue: deque = deque()  # (timestamp, event_type, event_data)
        self.pending_events: Dict[str, List[Dict[str, Any]]] = {}  # order_id -> list of pending events
        
        # Idempotency tracking
        self.processed_fill_ids: set = set()  # Track processed fill IDs
        self.processed_order_ids: set = set()  # Track processed order status updates
        
        # Chaos statistics
        self.chaos_stats = {
            "out_of_order_events": 0,
            "duplicate_events_ignored": 0,
            "late_cancel_acks": 0,
            "cancel_rejections": 0,
            "partial_fills": 0,
            "delayed_events": 0,
        }
        
        if self.chaos_enabled:
            logger.warning(f"⚠️ [{self.worker_name}] CHAOS MODE ENABLED - Adversarial testing active")
    
    def _generate_fill_id(self, order_id: str, fill_sequence: int = 0) -> str:
        """Generate unique fill ID for idempotency"""
        return f"FILL_{order_id}_{fill_sequence}_{int(time.time() * 1000)}"
    
    def _check_fill_idempotency(self, fill_id: str) -> bool:
        """Check if fill ID was already processed"""
        if fill_id in self.processed_fill_ids:
            self.chaos_stats["duplicate_events_ignored"] += 1
            logger.warning(
                f"🔄 [{self.worker_name}] Duplicate fill ignored: fill_id={fill_id}"
            )
            return False  # Already processed
        self.processed_fill_ids.add(fill_id)
        return True  # New fill
    
    def _check_order_status_idempotency(self, order_id: str, status: str, event_id: str) -> bool:
        """Check if order status update was already processed"""
        key = f"{order_id}:{status}:{event_id}"
        if key in self.processed_order_ids:
            self.chaos_stats["duplicate_events_ignored"] += 1
            logger.warning(
                f"🔄 [{self.worker_name}] Duplicate order status ignored: "
                f"order_id={order_id}, status={status}, event_id={event_id}"
            )
            return False  # Already processed
        self.processed_order_ids.add(key)
        return True  # New update
    
    def _apply_latency(self, event_type: str) -> float:
        """Apply random latency to event"""
        if not self.latency_enabled:
            return 0.0
        
        delay = random.uniform(self.latency_min, self.latency_max)
        self.chaos_stats["delayed_events"] += 1
        logger.debug(
            f"⏱️ [{self.worker_name}] Latency applied: {event_type} delayed by {delay:.2f}s"
        )
        return delay
    
    def _should_duplicate(self) -> bool:
        """Determine if event should be duplicated"""
        if not self.duplicate_enabled:
            return False
        return random.random() < self.duplicate_probability
    
    def _should_partial_fill(self) -> bool:
        """Determine if order should partially fill"""
        if not self.partial_fill_enabled:
            return False
        return random.random() < self.partial_fill_probability
    
    def _should_reject_cancel(self) -> bool:
        """Determine if cancel should be rejected"""
        if not self.cancel_rejection_enabled:
            return False
        return random.random() < self.cancel_rejection_probability
    
    def _simulate_fill_deterministic(self, order_id: str, order_data: Dict[str, Any]):
        """Override: Simulate fill with chaos (partial fills, latency, duplicates)"""
        try:
            import json
            
            # Apply latency
            latency = self._apply_latency("FILL")
            if latency > 0:
                time.sleep(latency)
            
            # Check if should partial fill
            should_partial = self._should_partial_fill()
            
            intent_type = order_data.get("intent_type", "")
            fill_probability = {
                "HARD_DERISK": 1.0,
                "SOFT_DERISK": 0.9,
                "CAP_RECOVERY": 1.0,
            }.get(intent_type, 0.5)
            
            # Use deterministic seed for reproducibility
            seed = hash(order_id) % (2**32)
            random.seed(seed)
            
            if random.random() < fill_probability:
                total_quantity = order_data["quantity"]
                
                if should_partial and total_quantity > 1:
                    # Partial fill
                    fill_pct = random.uniform(self.partial_fill_min_pct, self.partial_fill_max_pct)
                    filled_quantity = max(1, int(total_quantity * fill_pct))
                    remaining_quantity = total_quantity - filled_quantity
                    self.chaos_stats["partial_fills"] += 1
                    
                    logger.info(
                        f"📊 [{self.worker_name}] PARTIAL FILL: "
                        f"order_id={order_id}, filled={filled_quantity}/{total_quantity}"
                    )
                else:
                    # Full fill
                    filled_quantity = total_quantity
                    remaining_quantity = 0
                
                limit_price = order_data.get("limit_price")
                if limit_price:
                    avg_fill_price = limit_price
                else:
                    avg_fill_price = 100.0
                
                # Generate fill ID for idempotency
                fill_id = self._generate_fill_id(order_id, 0)
                
                # Publish PARTIAL_FILL or FILLED event
                self._publish_fill_event(
                    order_id=order_id,
                    order_data=order_data,
                    filled_quantity=filled_quantity,
                    remaining_quantity=remaining_quantity,
                    avg_fill_price=avg_fill_price,
                    fill_id=fill_id,
                    is_partial=(remaining_quantity > 0)
                )
                
                # If partial fill, simulate remaining fill later (or replace)
                if remaining_quantity > 0:
                    # Store remaining quantity for potential later fill
                    order_data["remaining_quantity"] = remaining_quantity
                    order_data["status"] = "PARTIAL_FILL"
                    order_data["filled_quantity"] = filled_quantity
                    order_data["avg_fill_price"] = avg_fill_price
                    
                    # Update registry
                    self.state_store.update_state("orders_registry", {
                        order_id: json.dumps(order_data)
                    })
                else:
                    # Full fill - unregister
                    order_data["status"] = "FILLED"
                    order_data["filled_quantity"] = filled_quantity
                    order_data["avg_fill_price"] = avg_fill_price
                    order_data["filled_at"] = time.time()
                    
                    self.state_store.update_state("orders_registry", {
                        order_id: json.dumps(order_data)
                    })
                    self._unregister_order(order_id, order_data)
                
                # Simulate duplicate fill (if enabled)
                if self._should_duplicate():
                    logger.warning(
                        f"🔄 [{self.worker_name}] Simulating duplicate fill: order_id={order_id}"
                    )
                    # Try to publish duplicate (should be ignored by idempotency)
                    self._publish_fill_event(
                        order_id=order_id,
                        order_data=order_data,
                        filled_quantity=filled_quantity,
                        remaining_quantity=remaining_quantity,
                        avg_fill_price=avg_fill_price,
                        fill_id=fill_id,  # Same fill_id = duplicate
                        is_partial=(remaining_quantity > 0)
                    )
            else:
                logger.debug(f"⏳ [{self.worker_name}] Order not filled: {order_id}")
        
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error simulating fill: {e}", exc_info=True)
    
    def _publish_fill_event(
        self,
        order_id: str,
        order_data: Dict[str, Any],
        filled_quantity: int,
        remaining_quantity: int,
        avg_fill_price: float,
        fill_id: str,
        is_partial: bool
    ):
        """Publish fill event with idempotency check"""
        # Check idempotency
        if not self._check_fill_idempotency(fill_id):
            return  # Duplicate, ignore
        
        classification = order_data.get("classification", "")
        bucket = order_data.get("bucket", "LT")
        effect = order_data.get("effect", "DECREASE")
        direction = order_data.get("direction", "LONG")
        risk_delta_notional = order_data.get("risk_delta_notional", 0.0)
        risk_delta_gross_pct = order_data.get("risk_delta_gross_pct", 0.0)
        position_context = order_data.get("position_context_at_intent", {})
        intent_id = order_data.get("intent_id", "")
        order_action = order_data.get("action", "")
        account_id = position_context.get("account_id", "HAMMER")
        
        if is_partial:
            action = "PARTIAL_FILL"
            status = "PARTIAL_FILL"
        else:
            action = "FILLED"
            status = "FILLED"
        
        fill_event = OrderEvent.create(
            order_id=order_id,
            symbol=order_data["symbol"],
            action=action,
            quantity=order_data["quantity"],  # Original quantity
            order_type="LIMIT" if order_data.get("limit_price") else "MARKET",
            classification=classification,
            bucket=bucket,
            effect=effect,
            dir=direction,
            risk_delta_notional=risk_delta_notional,
            risk_delta_gross_pct=risk_delta_gross_pct,
            position_context_at_intent=position_context,
            limit_price=order_data.get("limit_price"),
            filled_quantity=filled_quantity,
            avg_fill_price=avg_fill_price,
            status=status,
            intent_id=intent_id,
            order_action=order_action,
            account_id=account_id,
            metadata={"fill_id": fill_id, "remaining_quantity": remaining_quantity}
        )
        
        self.event_log.publish("orders", fill_event)
        logger.info(
            f"✅ [{self.worker_name}] Fill event published: "
            f"order_id={order_id}, filled={filled_quantity}, fill_id={fill_id}"
        )
    
    def cancel_order(self, order_id: str, reason: str = "User request") -> bool:
        """Override: Cancel order with chaos (rejection, latency, out-of-order)"""
        try:
            import json
            
            # Apply latency
            latency = self._apply_latency("CANCEL")
            if latency > 0:
                time.sleep(latency)
            
            registry_data = self.state_store.get_state("orders_registry")
            if not registry_data:
                logger.warning(f"⚠️ [{self.worker_name}] Order not found: {order_id}")
                return False
            
            order_data_str = registry_data.get(order_id)
            if not order_data_str:
                logger.warning(f"⚠️ [{self.worker_name}] Order not found: {order_id}")
                return False
            
            order_data = json.loads(order_data_str) if isinstance(order_data_str, str) else order_data_str
            current_status = order_data.get("status", "")
            
            # Check if cancel should be rejected
            if self._should_reject_cancel():
                # Simulate cancel rejection (order already filled or too late)
                self.chaos_stats["cancel_rejections"] += 1
                logger.warning(
                    f"❌ [{self.worker_name}] Cancel REJECTED: "
                    f"order_id={order_id}, reason='Order already filled or too late'"
                )
                
                # Publish CANCEL_REJECTED event
                classification = order_data.get("classification", "")
                bucket = order_data.get("bucket", "LT")
                effect = order_data.get("effect", "DECREASE")
                direction = order_data.get("direction", "LONG")
                risk_delta_notional = order_data.get("risk_delta_notional", 0.0)
                risk_delta_gross_pct = order_data.get("risk_delta_gross_pct", 0.0)
                position_context = order_data.get("position_context_at_intent", {})
                intent_id = order_data.get("intent_id", "")
                
                reject_event = OrderEvent.create(
                    order_id=order_id,
                    symbol=order_data["symbol"],
                    action="CANCEL_REJECTED",
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
                    status="CANCEL_REJECTED",
                    intent_id=intent_id,
                    metadata={"reject_reason": "Order already filled or too late"}
                )
                self.event_log.publish("orders", reject_event)
                return False
            
            # Normal cancel logic
            if current_status in ["FILLED", "CANCELED", "REJECTED", "CANCEL_REJECTED"]:
                logger.warning(
                    f"⚠️ [{self.worker_name}] Order already closed: "
                    f"order_id={order_id}, status={current_status}"
                )
                return False
            
            # Update status
            order_data["status"] = "CANCELED"
            order_data["canceled_at"] = time.time()
            order_data["cancel_reason"] = reason
            
            # Update registry
            self.state_store.update_state("orders_registry", {
                order_id: json.dumps(order_data)
            })
            
            # Publish CANCELED event
            classification = order_data.get("classification", "")
            bucket = order_data.get("bucket", "LT")
            effect = order_data.get("effect", "DECREASE")
            direction = order_data.get("direction", "LONG")
            risk_delta_notional = order_data.get("risk_delta_notional", 0.0)
            risk_delta_gross_pct = order_data.get("risk_delta_gross_pct", 0.0)
            position_context = order_data.get("position_context_at_intent", {})
            intent_id = order_data.get("intent_id", "")
            
            event_id = str(uuid.uuid4())
            if not self._check_order_status_idempotency(order_id, "CANCELED", event_id):
                return True  # Already processed
            
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
                metadata={"event_id": event_id}
            )
            self.event_log.publish("orders", cancel_event)
            
            # Unregister
            self._unregister_order(order_id, order_data)
            
            logger.info(f"✅ [{self.worker_name}] Order canceled: {order_id}")
            return True
        
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error canceling order: {e}", exc_info=True)
            return False
    
    def process_intent(self, intent_data: Dict[str, str]):
        """Override: Process intent with out-of-order simulation"""
        try:
            # Apply latency to ACCEPTED event
            latency = self._apply_latency("ACCEPTED")
            if latency > 0:
                time.sleep(latency)
            
            # Call parent implementation
            super().process_intent(intent_data)
        
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error processing intent: {e}", exc_info=True)
    
    def get_chaos_stats(self) -> Dict[str, Any]:
        """Get chaos simulation statistics"""
        return self.chaos_stats.copy()
    
    def reset_chaos_stats(self):
        """Reset chaos statistics"""
        self.chaos_stats = {
            "out_of_order_events": 0,
            "duplicate_events_ignored": 0,
            "late_cancel_acks": 0,
            "cancel_rejections": 0,
            "partial_fills": 0,
            "delayed_events": 0,
        }
        self.processed_fill_ids.clear()
        self.processed_order_ids.clear()



