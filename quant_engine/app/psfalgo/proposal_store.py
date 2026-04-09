"""
Proposal Store - Stores and manages OrderProposals

Stores proposals for human review and tracking.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from collections import deque

from app.core.logger import logger
from app.psfalgo.proposal_models import OrderProposal, ProposalStatus
import json


class ProposalStore:
    """
    ProposalStore - stores OrderProposals for human review (Redis Backed).
    
    Responsibilities:
    - Store proposals (Shared State via Redis)
    - Track proposal lifecycle
    - Provide query interface
    """
    
    KEY_DATA = "proposals:data"      # Hash: id -> json
    KEY_TIMELINE = "proposals:timeline" # ZSet: id -> timestamp
    
    def __init__(self, max_proposals: int = 5000):
        """
        Initialize Proposal Store.
        Connects to Redis.
        
        Note: Increased from 1000 to 5000 to handle high-volume MM proposals
        while preserving LT_TRIM/KARBOTU proposals.
        """
        self.max_proposals = max_proposals
        self.redis = None
        
        try:
            from app.core.redis_client import get_redis_client
            client = get_redis_client()
            if client:
                self.redis = client.sync  # Use sync client
                logger.debug("✅ [PROPOSAL_STORE] Connected to Redis")
            else:
                logger.warning("⚠️ [PROPOSAL_STORE] Redis client not available - Store will fail")
        except Exception as e:
            logger.error(f"❌ [PROPOSAL_STORE] Failed to connect to Redis: {e}")

    def add_proposal(self, proposal: OrderProposal) -> str:
        """Add proposal to Redis."""
        if not self.redis:
            return ""
        proposal_id = self._generate_proposal_id(proposal)
        uniq_key = self._uniq_key(proposal)

        # LT_STAGE: ayni (symbol, side, qty, price) icin sadece en buyuk stage onerilir.
        # Mevcut proposal daha yuksek stage ise yeniyi yazma (STAGE_4 > STAGE_2 > ...).
        existing_id = self.redis.hget("proposals:unique_index", uniq_key)
        if existing_id is not None:
            eid = existing_id.decode("utf-8") if isinstance(existing_id, bytes) else existing_id
            existing = self.get_proposal(eid)
            if existing and getattr(existing, "status", None) == ProposalStatus.PROPOSED.value:
                if self.get_lt_stage_rank(existing) > self.get_lt_stage_rank(proposal):
                    logger.debug(
                        f"[PROPOSAL_STORE] Skip add (existing has higher LT_STAGE): {uniq_key}"
                    )
                    return ""
        # Uniq: ayni emirde eskisi silinir, yenisi yazilir. Book degismesi farkli kayit saymaz.
        self._remove_existing_similar_proposal(proposal)
        
        # Serialization
        try:
            data_json = json.dumps(proposal.to_dict())
            # Pipeline for availability
            pipe = self.redis.pipeline()
            pipe.hset(self.KEY_DATA, proposal_id, data_json)
            pipe.zadd(self.KEY_TIMELINE, {proposal_id: proposal.proposal_ts.timestamp()})
            pipe.hset("proposals:unique_index", uniq_key, proposal_id)
            
            # Cleanup inline if too big (probabilistic or fixed interval?)
            # Let's do loose cleanup
            pipe.zcard(self.KEY_TIMELINE)
            results = pipe.execute()
            count = results[3]  # zcard result
            if count > self.max_proposals + 50: # Buffet buffer
                self._cleanup_old_proposals()
                
            logger.info(f"[PROPOSAL_STORE] Added proposal: {proposal_id}")
            return proposal_id
            
        except Exception as e:
            logger.error(f"[PROPOSAL_STORE] Error adding proposal: {e}")
            return ""

    def _generate_proposal_id(self, proposal: OrderProposal) -> str:
        return f"{proposal.cycle_id}_{proposal.symbol}_{proposal.side}_{proposal.proposal_ts.timestamp()}"
    
    def get_proposal_id(self, proposal: OrderProposal) -> str:
        return self._generate_proposal_id(proposal)
    
    def get_proposal(self, proposal_id: str) -> Optional[OrderProposal]:
        """Get proposal by ID"""
        if not self.redis: return None
        data = self.redis.hget(self.KEY_DATA, proposal_id)
        if data:
            try:
                return OrderProposal.from_dict(json.loads(data))
            except Exception as e:
                logger.error(f"[PROPOSAL_STORE] Deserialization error: {e}")
        return None
    
    def get_all_proposals(
        self,
        status: Optional[str] = None,
        engine: Optional[str] = None,
        cycle_id: Optional[int] = None,
        account_id: Optional[str] = None,
        limit: int = 100
    ) -> List[OrderProposal]:
        """Get proposals with filters."""
        if not self.redis: return []
        
        # When filtering by engine (LT_TRIM, KARBOTU, etc.), scan a much larger window
        # so engine-specific tabs don't miss proposals buried under many MM proposals.
        scan_size = limit * 20 if engine else limit * 2
        scan_size = min(scan_size, 5000)  # Cap to avoid huge scans
        ids = self.redis.zrevrange(self.KEY_TIMELINE, 0, scan_size - 1)
        if not ids: return []
        
        # Fetch data
        raw_data = self.redis.hmget(self.KEY_DATA, ids)
        
        proposals = []
        for d in raw_data:
            if d:
                try:
                    p = OrderProposal.from_dict(json.loads(d))
                    
                    # Filters
                    if status and p.status != status: continue
                    if engine and p.engine != engine: continue
                    if cycle_id is not None and p.cycle_id != cycle_id: continue
                    if account_id and getattr(p, 'account_id', None) and p.account_id != account_id: continue
                    
                    proposals.append(p)
                    if len(proposals) >= limit: break
                    
                except Exception:
                    continue
        
        return proposals
    
    def get_latest_proposals(self, limit: int = 10) -> List[OrderProposal]:
        return self.get_all_proposals(limit=limit)
    
    def get_pending_proposals(self) -> List[OrderProposal]:
        return self.get_all_proposals(status=ProposalStatus.PROPOSED.value, limit=1000)

    def get_pending_count(self) -> int:
        """Get count of pending proposals (PROPOSED status)"""
        return len(self.get_pending_proposals())

    def update_proposal_status(self, proposal_id: str, status: str, human_action: Optional[str] = None) -> bool:
        if not self.redis: return False
        
        p = self.get_proposal(proposal_id)
        if not p:
            logger.warning(f"[PROPOSAL_STORE] Proposal not found: {proposal_id}")
            return False
            
        p.status = status
        p.human_action = human_action
        p.human_action_ts = datetime.now()
        
        # Save back
        try:
            self.redis.hset(self.KEY_DATA, proposal_id, json.dumps(p.to_dict()))
            logger.debug(f"[PROPOSAL_STORE] Updated proposal {proposal_id}")
            return True
        except Exception as e:
            logger.error(f"[PROPOSAL_STORE] Update error: {e}")
            return False

    def _cleanup_old_proposals(self):
        """Remove old proposals > max_proposals"""
        if not self.redis: return
        
        try:
            count = self.redis.zcard(self.KEY_TIMELINE)
            if count > self.max_proposals:
                to_remove = count - self.max_proposals
                # Get IDs to remove (oldest -> 0 to to_remove)
                ids_to_remove = self.redis.zrange(self.KEY_TIMELINE, 0, to_remove - 1)
                
                if ids_to_remove:
                    pipe = self.redis.pipeline()
                    pipe.hdel(self.KEY_DATA, *ids_to_remove)
                    pipe.zrem(self.KEY_TIMELINE, *ids_to_remove)
                    
                    # ALSO CLEANUP UNIQUE INDEX?
                    # This is hard because we don't know the keys from IDs easily without reverse lookup.
                    # Ignore for now, it's just a lookup pointer. It will be overwritten or return stale ID (which we check).
                    
                    pipe.execute()
                    # logger.debug(f"[PROPOSAL_STORE] Cleaned up {len(ids_to_remove)} old proposals")
        except Exception as e:
            logger.error(f"[PROPOSAL_STORE] Cleanup error: {e}")

    def _find_duplicate(self, new_proposal: OrderProposal) -> Optional[OrderProposal]:
        # Not efficiently implemented in Redis without secondary index.
        # Skipping for now - unique ID usually sufficient for dedupe by cycle/ts.
        return None

    def clear_pending_proposals_with_cycle_id(self, cycle_id: int) -> int:
        """
        Remove all PENDING proposals with the given cycle_id.
        Used by XNL to replace its previous batch (cycle_id=-1) before writing a new one,
        so the same batch does not accumulate repeatedly. RUNALL uses positive cycle_id.
        Returns number of proposals removed.
        """
        if not self.redis:
            return 0
        removed = 0
        try:
            all_pending = self.get_all_proposals(status=ProposalStatus.PROPOSED.value, limit=5000)
            to_remove = [p for p in all_pending if p.cycle_id == cycle_id]
            if not to_remove:
                return 0
            pipe = self.redis.pipeline()
            index_key = "proposals:unique_index"
            for p in to_remove:
                pid = self._generate_proposal_id(p)
                pipe.hdel(self.KEY_DATA, pid)
                pipe.zrem(self.KEY_TIMELINE, pid)
                uniq_key = self._uniq_key(p)
                pipe.hdel(index_key, uniq_key)
                removed += 1
            pipe.execute()
            if removed > 0:
                logger.debug(f"[PROPOSAL_STORE] Cleared {removed} PENDING proposals with cycle_id={cycle_id}")
        except Exception as e:
            logger.error(f"[PROPOSAL_STORE] Error clearing proposals by cycle_id: {e}")
        return removed

    def _uniq_key(self, proposal: OrderProposal) -> str:
        """
        Uniqueness key: symbol, side, qty, price, book.
        Kosullar (engine/stage) degisebilir; ayni emir = birebir ayni hisse, yon, lot, fiyat, long/short.
        """
        return self.get_uniq_key(proposal)

    def get_uniq_key(self, proposal: OrderProposal) -> str:
        """
        Tekillik: ayni hisse + ayni yön + ayni lot = tek öneri; sadece en güncel kalir.
        Her zaman (symbol, side, qty). Fiyat ve 727→427 gibi pozisyon bilgisi keyde yok.
        Böylece "300 SELL @ 25.98" ve "300 SELL @ 25.97" (ikisi de 727→427) ayni key = FGN:SELL:300.
        """
        sym = (proposal.symbol or "").strip().upper()
        side = (proposal.side or "SELL").upper()
        qty = int(proposal.qty) if proposal.qty is not None else 0
        return f"{sym}:{side}:{qty}"

    def get_lt_stage_rank(self, proposal: OrderProposal) -> int:
        """
        LT_STAGE sira: 4 > 3 > 2 > 1 > SMALL.
        Ayni (symbol, side, qty, price) icin sadece en buyuk stage onerilir; 2sini birden yazmayiz.
        reason veya order_subtype icinde LT_STAGE_4, LT_STAGE_3, ... LT_STAGE_SMALL aranir.
        """
        text = (
            (getattr(proposal, "reason", None) or "")
            + " "
            + (getattr(proposal, "order_subtype", None) or "")
        ).upper()
        if "LT_STAGE_4" in text:
            return 4
        if "LT_STAGE_3" in text:
            return 3
        if "LT_STAGE_2" in text:
            return 2
        if "LT_STAGE_1" in text:
            return 1
        if "LT_STAGE_SMALL" in text:
            return 0
        return -1

    def _remove_existing_similar_proposal(self, new_proposal: OrderProposal):
        """
        Remove any existing PENDING proposal with IDENTICAL (symbol, side, qty, price).
        Book degismesi farkli kayit saymaz; ayni emirde eskisi silinir.
        """
        if not self.redis:
            return
        try:
            uniq_key = self._uniq_key(new_proposal)
            index_key = "proposals:unique_index"
            existing_id = self.redis.hget(index_key, uniq_key)
            if existing_id is not None:
                if isinstance(existing_id, bytes):
                    existing_id = existing_id.decode("utf-8")
                old_p_json = self.redis.hget(self.KEY_DATA, existing_id)
                if old_p_json:
                    try:
                        raw = old_p_json.decode("utf-8") if isinstance(old_p_json, bytes) else old_p_json
                        old_p = json.loads(raw)
                        if old_p.get("status") == ProposalStatus.PROPOSED.value:
                            pipe = self.redis.pipeline()
                            pipe.hdel(self.KEY_DATA, existing_id)
                            pipe.zrem(self.KEY_TIMELINE, existing_id)
                            pipe.hdel(index_key, uniq_key)
                            pipe.execute()
                            logger.debug(f"[PROPOSAL_STORE] Removed identical proposal {existing_id} for {uniq_key}")
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"[PROPOSAL_STORE] Error removing similar: {e}")

    def get_stats(self) -> Dict[str, Any]:
        return {} # Not critical



# Global instance
_proposal_store: Optional[ProposalStore] = None


def get_proposal_store() -> Optional[ProposalStore]:
    """Get global ProposalStore instance"""
    return _proposal_store


def initialize_proposal_store(max_proposals: int = 5000):
    """Initialize global ProposalStore instance"""
    global _proposal_store
    _proposal_store = ProposalStore(max_proposals=max_proposals)
    logger.info(f"ProposalStore initialized with capacity: {max_proposals}")

