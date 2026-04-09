"""
Order Queue Worker

CRITICAL: Processes orders from Redis queue and sends via ExecutionRouter.
This ensures single IBKR connection point and no HTTP timeouts.

Flow:
1. RevnBookCheck/Terminals → Redis Queue (psfalgo:orders:pending)
2. OrderQueueWorker → Reads from queue
3. ExecutionRouter → Sends to IBKR/Hammer
4. Status → Redis (psfalgo:orders:status:{order_id})
"""
import asyncio
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any
from loguru import logger


class OrderQueueWorker:
    """
    Worker that processes orders from Redis queue.
    
    This is the SINGLE POINT OF ORDER EXECUTION:
    - All terminals write orders to Redis queue
    - Backend worker processes them via ExecutionRouter
    - Single IBKR connection (no conflicts)
    """
    
    def __init__(self):
        self.running = False
        self.queue_key = "psfalgo:orders:pending"
        self.status_prefix = "psfalgo:orders:status:"
        self.process_interval = 1.0  # Check queue every 1 second
        self.max_retries = 3
        self.retry_delay = 2.0  # seconds
    
    async def run(self):
        """Main worker loop"""
        logger.info("[OrderQueueWorker] Starting... (processes orders from Redis queue)")
        self.running = True
        
        while self.running:
            try:
                await self._process_order_queue()
                await asyncio.sleep(self.process_interval)
            except Exception as e:
                logger.error(f"[OrderQueueWorker] Error: {e}", exc_info=True)
                await asyncio.sleep(self.process_interval)
    
    async def _process_order_queue(self):
        """Process orders from Redis queue"""
        try:
            from app.core.redis_client import get_redis_client
            
            redis_client = get_redis_client()
            if not redis_client or not hasattr(redis_client, 'sync'):
                return
            
            redis = redis_client.sync
            
            # Pop order from queue (BLPOP - blocking pop, waits for order)
            result = redis.blpop(self.queue_key, timeout=1)  # 1 second timeout
            
            if not result:
                return  # No orders in queue
            
            queue_name, order_json = result
            order_data = json.loads(order_json.decode() if isinstance(order_json, bytes) else order_json)
            
            # Process order
            await self._execute_order(order_data, redis)
            
        except Exception as e:
            logger.error(f"[OrderQueueWorker] Queue processing error: {e}", exc_info=True)
    
    async def _execute_order(self, order_data: Dict[str, Any], redis):
        """Execute order via ExecutionRouter"""
        order_id = order_data.get('order_id') or str(uuid.uuid4())
        symbol = order_data.get('symbol')
        action = order_data.get('action')  # BUY/SELL
        qty = order_data.get('qty')
        price = order_data.get('price')
        account_id = order_data.get('account_id')
        source = order_data.get('source', 'UNKNOWN')
        
        logger.info(
            f"[OrderQueueWorker] Processing order: {order_id} | "
            f"{action} {qty} {symbol} @ {price} | Account: {account_id} | Source: {source}"
        )
        
        # Update status: PROCESSING
        self._update_order_status(redis, order_id, {
            'status': 'PROCESSING',
            'message': 'Order queued for execution',
            'timestamp': datetime.now().isoformat()
        })
        
        try:
            # Set trading context to correct account
            from app.trading.trading_account_context import get_trading_context, TradingAccountMode
            ctx = get_trading_context()
            
            if account_id:
                try:
                    mode_enum = TradingAccountMode.HAMPRO if account_id in ("HAMPRO", "HAMMER_PRO") else TradingAccountMode(account_id)
                    if ctx.trading_mode != mode_enum:
                        ctx.set_trading_mode(mode_enum)
                        logger.info(f"[OrderQueueWorker] Set trading context to {mode_enum.value}")
                except ValueError:
                    logger.warning(f"[OrderQueueWorker] Invalid account_id: {account_id}")
            
            # Prepare order plan
            order_plan = {
                'symbol': symbol,
                'action': action,
                'size': int(qty),
                'price': float(price),
                'style': order_data.get('order_type', 'LIMIT'),
                'psfalgo_source': True,
                'psfalgo_action': 'REV_ORDER',
                'strategy_tag': order_data.get('strategy_tag', 'REV_TP')
            }
            
            gate_status = {'gate_status': 'AUTO_APPROVE'}  # Auto-approve for REV orders
            
            # Execute via ExecutionRouter (with retry for transient failures)
            from app.execution.execution_router import get_execution_router
            router = get_execution_router()
            
            max_exec_retries = 2
            result = None
            for exec_attempt in range(max_exec_retries + 1):
                # Run in executor to avoid blocking
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: router.handle(
                        order_plan=order_plan,
                        gate_status=gate_status,
                        user_action='APPROVE',
                        symbol=symbol
                    )
                )
                
                if result.get('execution_status') == 'EXECUTED':
                    break  # Success
                
                # Check if retryable
                error_reason = result.get('execution_reason') or result.get('provider_error') or ''
                is_retryable = 'Hammer Error' in str(error_reason) or 'No Response' in str(error_reason)
                is_duplicate = 'Duplicate' in str(error_reason)
                
                if is_retryable and not is_duplicate and exec_attempt < max_exec_retries:
                    logger.warning(
                        f"[OrderQueueWorker] Retrying order {order_id} (attempt {exec_attempt + 2}/{max_exec_retries + 1}) "
                        f"after transient error: {error_reason}"
                    )
                    await asyncio.sleep(3.0)
                else:
                    break  # Non-retryable or max retries reached
            
            # Update status based on final result
            if result.get('execution_status') == 'EXECUTED':
                ibkr_order_id = result.get('order_id', '')
                self._update_order_status(redis, order_id, {
                    'status': 'SUBMITTED',
                    'ibkr_order_id': str(ibkr_order_id),
                    'message': f'Order submitted successfully',
                    'timestamp': datetime.now().isoformat(),
                    'symbol': symbol,
                    'action': action,
                    'qty': qty,
                    'price': price
                })
                logger.info(
                    f"[OrderQueueWorker] \u2705 Order submitted: {order_id} \u2192 IBKR OrderID: {ibkr_order_id} | "
                    f"{action} {qty} {symbol} @ {price}"
                )
            else:
                error_reason = result.get('execution_reason') or result.get('provider_error') or 'Unknown error'
                self._update_order_status(redis, order_id, {
                    'status': 'FAILED',
                    'message': f'Order execution failed: {error_reason}',
                    'error': error_reason,
                    'timestamp': datetime.now().isoformat()
                })
                logger.error(
                    f"[OrderQueueWorker] \u274c Order failed: {order_id} | Reason: {error_reason}"
                )
                
        except Exception as e:
            logger.error(f"[OrderQueueWorker] Order execution error: {e}", exc_info=True)
            self._update_order_status(redis, order_id, {
                'status': 'ERROR',
                'message': f'Order execution error: {str(e)}',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })
    
    def _update_order_status(self, redis, order_id: str, status_data: Dict[str, Any]):
        """Update order status in Redis"""
        try:
            status_key = f"{self.status_prefix}{order_id}"
            redis.setex(
                status_key,
                3600,  # 1 hour TTL
                json.dumps(status_data)
            )
        except Exception as e:
            logger.warning(f"[OrderQueueWorker] Failed to update order status: {e}")


# Global instance
_order_queue_worker: Optional[OrderQueueWorker] = None


def get_order_queue_worker() -> Optional[OrderQueueWorker]:
    """Get global OrderQueueWorker instance"""
    return _order_queue_worker


def start_order_queue_worker():
    """Start the order queue worker"""
    global _order_queue_worker
    
    if _order_queue_worker and _order_queue_worker.running:
        logger.warning("[OrderQueueWorker] Already running")
        return
    
    _order_queue_worker = OrderQueueWorker()
    
    # Start in background
    import asyncio
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_order_queue_worker.run())
        logger.info("[OrderQueueWorker] ✅ Started")
    except RuntimeError:
        # No running loop - create task via asyncio
        asyncio.create_task(_order_queue_worker.run())
        logger.info("[OrderQueueWorker] ✅ Started (via asyncio.create_task)")
    except Exception as e:
        logger.error(f"[OrderQueueWorker] Failed to start: {e}")
