"""
Intent Store
In-memory store for PSFALGO Intentions.
"""

from typing import Optional, List, Dict
from datetime import datetime, timedelta
from collections import deque
from app.core.logger import logger
from app.psfalgo.intent_models import Intent, IntentStatus, IntentAction


class IntentStore:
    """
    Intent Store - In-memory ring buffer for intents.
    
    Features:
    - Ring buffer (last 1000 intents)
    - Per-symbol latest intent tracking
    - Status filtering
    - Expiration (optional)
    """
    
    def __init__(self, max_size: int = 1000, expiration_hours: int = 24, ttl_seconds: int = 90):
        """
        Initialize Intent Store.
        
        Args:
            max_size: Maximum number of intents to keep (ring buffer)
            expiration_hours: Intent expiration time in hours (for cleanup)
            ttl_seconds: Intent TTL in seconds (for expiration status)
        """
        self.max_size = max_size
        self.expiration_hours = expiration_hours
        self.ttl_seconds = ttl_seconds
        
        # Ring buffer (FIFO)
        self._intents: deque = deque(maxlen=max_size)
        
        # Per-symbol latest intent (for quick lookup)
        self._latest_intent: Dict[str, Intent] = {}
        
        # Index by status (for fast filtering)
        self._status_index: Dict[IntentStatus, List[str]] = {
            status: [] for status in IntentStatus
        }
        
        # Index by symbol (for fast lookup)
        self._symbol_index: Dict[str, List[str]] = {}
        
        logger.info(f"[INTENT_STORE] Initialized (max_size={max_size}, expiration={expiration_hours}h)")
    
    def add_intent(self, intent: Intent) -> bool:
        """
        Add intent to store.
        
        Args:
            intent: Intent to add
            
        Returns:
            True if added successfully
        """
        try:
            # Check if intent already exists (by ID)
            if any(i.id == intent.id for i in self._intents):
                logger.warning(f"[INTENT_STORE] Intent {intent.id} already exists, skipping")
                return False
            
            # Add to ring buffer
            self._intents.append(intent)
            
            # Update latest intent for symbol
            self._latest_intent[intent.symbol] = intent
            
            # Update status index
            self._status_index[intent.status].append(intent.id)
            
            # Update symbol index
            if intent.symbol not in self._symbol_index:
                self._symbol_index[intent.symbol] = []
            self._symbol_index[intent.symbol].append(intent.id)
            
            logger.debug(f"[INTENT_STORE] Added intent {intent.id} for {intent.symbol} ({intent.action.value})")
            return True
            
        except Exception as e:
            logger.error(f"[INTENT_STORE] Error adding intent: {e}", exc_info=True)
            return False
    
    def get_intent(self, intent_id: str) -> Optional[Intent]:
        """Get intent by ID"""
        for intent in self._intents:
            if intent.id == intent_id:
                return intent
        return None
    
    def get_latest_intent(self, symbol: str) -> Optional[Intent]:
        """Get latest intent for symbol"""
        return self._latest_intent.get(symbol)
    
    def get_intents(
        self,
        status: Optional[IntentStatus] = None,
        symbol: Optional[str] = None,
        limit: int = 200
    ) -> List[Intent]:
        """
        Get intents with filters.
        
        Args:
            status: Filter by status (None = all)
            symbol: Filter by symbol (None = all)
            limit: Maximum number of intents to return
            
        Returns:
            List of intents (sorted by timestamp, newest first)
        """
        results = []
        
        # Filter by status
        if status:
            intent_ids = self._status_index.get(status, [])
            for intent_id in intent_ids:
                intent = self.get_intent(intent_id)
                if intent:
                    if symbol is None or intent.symbol == symbol:
                        results.append(intent)
        else:
            # All intents
            for intent in self._intents:
                if symbol is None or intent.symbol == symbol:
                    results.append(intent)
        
        # Sort by timestamp (newest first)
        results.sort(key=lambda x: x.timestamp, reverse=True)
        
        # Apply limit
        return results[:limit]
    
    def update_intent_status(
        self,
        intent_id: str,
        new_status: IntentStatus,
        reason: Optional[str] = None,
        execution_result: Optional[Dict] = None
    ) -> bool:
        """
        Update intent status.
        
        Args:
            intent_id: Intent ID
            new_status: New status
            reason: Optional reason for status change
            execution_result: Optional execution result
            
        Returns:
            True if updated successfully
        """
        intent = self.get_intent(intent_id)
        if not intent:
            logger.warning(f"[INTENT_STORE] Intent {intent_id} not found for status update")
            return False
        
        old_status = intent.status
        
        # Update status
        intent.status = new_status
        
        # Update timestamps
        if new_status == IntentStatus.APPROVED:
            intent.approved_at = datetime.now()
        elif new_status == IntentStatus.REJECTED:
            intent.rejected_at = datetime.now()
            intent.rejected_reason = reason
        elif new_status == IntentStatus.SENT:
            intent.sent_at = datetime.now()
            if execution_result:
                intent.execution_result = execution_result
        
        # Update indices
        if old_status != new_status:
            # Remove from old status index
            if intent_id in self._status_index.get(old_status, []):
                self._status_index[old_status].remove(intent_id)
            
            # Add to new status index
            if intent_id not in self._status_index.get(new_status, []):
                self._status_index[new_status].append(intent_id)
        
        logger.info(f"[INTENT_STORE] Updated intent {intent_id} status: {old_status.value} → {new_status.value}")
        return True
    
    def check_and_expire_intents(self) -> int:
        """
        Check and expire intents that exceed TTL.
        
        TTL starts from intent creation timestamp.
        Expired intents are marked as EXPIRED (not deleted).
        
        Returns:
            Number of intents expired
        """
        if self.ttl_seconds <= 0:
            return 0
        
        expired_before = datetime.now() - timedelta(seconds=self.ttl_seconds)
        expired_count = 0
        
        # Find and expire intents
        for intent in self._intents:
            # Only expire PENDING intents that exceed TTL
            if intent.status == IntentStatus.PENDING and intent.timestamp < expired_before:
                old_status = intent.status
                intent.status = IntentStatus.EXPIRED
                
                # Update indices
                if intent.id in self._status_index.get(old_status, []):
                    self._status_index[old_status].remove(intent.id)
                if intent.id not in self._status_index.get(IntentStatus.EXPIRED, []):
                    self._status_index[IntentStatus.EXPIRED].append(intent.id)
                
                expired_count += 1
                logger.debug(f"[INTENT_STORE] Intent {intent.id} expired (TTL: {self.ttl_seconds}s)")
        
        if expired_count > 0:
            logger.info(f"[INTENT_STORE] Expired {expired_count} intents (TTL: {self.ttl_seconds}s)")
        
        return expired_count
    
    def clear_expired(self) -> int:
        """
        Clear old expired intents (cleanup, not expiration).
        
        Returns:
            Number of intents cleared
        """
        if self.expiration_hours <= 0:
            return 0
        
        expired_before = datetime.now() - timedelta(hours=self.expiration_hours)
        cleared = 0
        
        # Find old expired intents to remove
        intents_to_remove = []
        for intent in self._intents:
            if intent.status == IntentStatus.EXPIRED and intent.timestamp < expired_before:
                intents_to_remove.append(intent.id)
        
        # Remove from store
        for intent_id in intents_to_remove:
            intent = self.get_intent(intent_id)
            if intent:
                self._intents.remove(intent)
                if intent.symbol in self._latest_intent and self._latest_intent[intent.symbol].id == intent_id:
                    del self._latest_intent[intent.symbol]
                if intent_id in self._status_index.get(IntentStatus.EXPIRED, []):
                    self._status_index[IntentStatus.EXPIRED].remove(intent_id)
                if intent.symbol in self._symbol_index and intent_id in self._symbol_index[intent.symbol]:
                    self._symbol_index[intent.symbol].remove(intent_id)
                cleared += 1
        
        if cleared > 0:
            logger.info(f"[INTENT_STORE] Cleared {cleared} old expired intents")
        
        return cleared
    
    def clear_all(self) -> int:
        """
        Clear all intents.
        
        Returns:
            Number of intents cleared
        """
        count = len(self._intents)
        self._intents.clear()
        self._latest_intent.clear()
        self._status_index = {status: [] for status in IntentStatus}
        self._symbol_index.clear()
        
        logger.info(f"[INTENT_STORE] Cleared all {count} intents")
        return count
    
    def get_stats(self) -> Dict:
        """Get store statistics"""
        stats = {
            'total_intents': len(self._intents),
            'by_status': {status.value: len(self._status_index.get(status, [])) for status in IntentStatus},
            'by_symbol': len(self._symbol_index),
            'latest_intents': len(self._latest_intent)
        }
        return stats


# Global singleton
_intent_store: Optional[IntentStore] = None


def get_intent_store() -> IntentStore:
    """Get singleton Intent Store instance"""
    global _intent_store
    if _intent_store is None:
        _intent_store = IntentStore()
    return _intent_store

