"""
Symbol Memory - Per-Symbol State Tracking (CACHE ONLY)

=== CRITICAL: CACHE ONLY ===
This module is for ANALYTICS and HISTORY tracking only.
order_controller._orders is the SINGLE SOURCE OF TRUTH for live orders.
DO NOT use symbol_memory.active_orders for order decisions.

=== PHASE 1 GUARD ===
When OBSERVE_ONLY mode is active, any attempt to write order state
will raise RuntimeError. We want LOUD failures, not silent corruption.

Tracks per-symbol (for observability):
- last_truth (bid/ask/last, timestamp, realism weights)
- last_decision (intent categories fired and why)
- last_orders (CACHE of order ids for analytics - READ ONLY in OBSERVE mode)
- venue_summary (FNRA vs OTHER distribution)
- last_fill_summary (fills, partials)
- cooldown flags (suppressed until time)
"""

import time
import json
import csv
import os
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
from pathlib import Path


# Global flag for OBSERVE_ONLY mode enforcement
_OBSERVE_ONLY_MODE: bool = False


def set_observe_only_mode(enabled: bool):
    """Set global OBSERVE_ONLY mode flag."""
    global _OBSERVE_ONLY_MODE
    _OBSERVE_ONLY_MODE = enabled
    if enabled:
        print("[SYMBOL_MEMORY] ⚠️ OBSERVE_ONLY mode ENABLED - order writes will raise RuntimeError")


def is_observe_only_mode() -> bool:
    """Check if OBSERVE_ONLY mode is active."""
    return _OBSERVE_ONLY_MODE


@dataclass
class TruthSnapshot:
    """Last truth data for a symbol."""
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    timestamp: float = 0.0
    realism_weight: float = 1.0
    venue_dominant: str = ""  # "FNRA" or "OTHER"
    
    @property
    def age_seconds(self) -> float:
        if self.timestamp <= 0:
            return 999999.0
        return time.time() - self.timestamp
    
    @property
    def spread(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return self.ask - self.bid
        return 0.0
    
    @property
    def is_stale(self) -> bool:
        return self.age_seconds > 90.0


@dataclass
class OrderRecord:
    """Active order tracking (CACHE ONLY - for analytics)."""
    order_id: str
    symbol: str
    side: str
    qty: int
    price: float
    intent_category: str
    created_ts: float
    ttl_seconds: float
    last_replace_ts: float = 0.0
    replace_count: int = 0
    reason: str = ""
    
    @property
    def is_expired(self) -> bool:
        return time.time() > (self.created_ts + self.ttl_seconds)
    
    @property
    def ttl_remaining(self) -> float:
        """Seconds until TTL expires."""
        return max(0, (self.created_ts + self.ttl_seconds) - time.time())
    
    @property
    def can_replace(self) -> bool:
        """Min 2.5s between replaces."""
        if self.last_replace_ts <= 0:
            return True
        return (time.time() - self.last_replace_ts) >= 2.5


@dataclass
class DecisionRecord:
    """Last decision made for a symbol."""
    intent_category: str
    action: str  # NEW, REPLACE, CANCEL, SKIP
    reason: str
    timestamp: float
    qty: int = 0
    price: float = 0.0


@dataclass 
class FillSummary:
    """Fill tracking."""
    total_filled: int = 0
    partial_fills: int = 0
    last_fill_ts: float = 0.0
    last_fill_price: float = 0.0


@dataclass
class SymbolMemory:
    """Complete state for a single symbol (CACHE ONLY)."""
    symbol: str
    position_qty: int = 0
    bucket: str = "LT"  # LT or ST
    
    # Truth data
    last_truth: TruthSnapshot = field(default_factory=TruthSnapshot)
    
    # Active orders (CACHE ONLY - for analytics)
    active_orders: Dict[str, OrderRecord] = field(default_factory=dict)
    
    # Decision history (last N)
    decision_history: List[DecisionRecord] = field(default_factory=list)
    
    # Fill summary
    fill_summary: FillSummary = field(default_factory=FillSummary)
    
    # Venue summary
    fnra_ratio: float = 0.5  # 0-1, ratio of FNRA trades
    
    # Cooldown
    suppressed_until: float = 0.0
    suppression_reason: str = ""
    
    # Exclusion
    is_excluded: bool = False
    
    @property
    def is_suppressed(self) -> bool:
        return time.time() < self.suppressed_until
    
    @property
    def active_order_count(self) -> int:
        return len(self.active_orders)
    
    @property
    def truth_age(self) -> float:
        return self.last_truth.age_seconds
    
    def add_decision(self, decision: DecisionRecord, max_history: int = 10):
        """Add decision to history, keeping only last N."""
        self.decision_history.append(decision)
        if len(self.decision_history) > max_history:
            self.decision_history = self.decision_history[-max_history:]
    
    def suppress(self, duration_seconds: float, reason: str):
        """Suppress decisions for this symbol."""
        self.suppressed_until = time.time() + duration_seconds
        self.suppression_reason = reason
    
    def snapshot(self) -> Dict[str, Any]:
        """Return serializable snapshot for logging."""
        return {
            'symbol': self.symbol,
            'position_qty': self.position_qty,
            'bucket': self.bucket,
            'bid': self.last_truth.bid,
            'ask': self.last_truth.ask,
            'last': self.last_truth.last,
            'truth_age_s': round(self.truth_age, 1),
            'is_stale': self.last_truth.is_stale,
            'active_orders': self.active_order_count,
            'is_suppressed': self.is_suppressed,
            'is_excluded': self.is_excluded,
            'fnra_ratio': round(self.fnra_ratio, 2),
            'last_action': self.decision_history[-1].action if self.decision_history else "",
            'last_category': self.decision_history[-1].intent_category if self.decision_history else "",
        }


class SymbolMemoryStore:
    """
    Manager for all symbol memories.
    
    CRITICAL: CACHE ONLY for analytics/history.
    order_controller is the SINGLE SOURCE OF TRUTH for orders.
    
    In OBSERVE_ONLY mode, order writes will raise RuntimeError.
    """
    
    def __init__(self, persist_dir: str = "logs"):
        self.memories: Dict[str, SymbolMemory] = {}
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(exist_ok=True)
        self._last_csv_flush: float = 0.0
        self._last_jsonl_write: float = 0.0
    
    def get(self, symbol: str) -> SymbolMemory:
        """Get or create memory for symbol."""
        if symbol not in self.memories:
            self.memories[symbol] = SymbolMemory(symbol=symbol)
        return self.memories[symbol]
    
    def update_truth(self, symbol: str, bid: float, ask: float, last: float,
                     realism_weight: float = 1.0, venue_dominant: str = ""):
        """Update truth data for symbol (always allowed)."""
        mem = self.get(symbol)
        mem.last_truth = TruthSnapshot(
            bid=bid,
            ask=ask,
            last=last,
            timestamp=time.time(),
            realism_weight=realism_weight,
            venue_dominant=venue_dominant
        )
    
    def update_position(self, symbol: str, qty: int, bucket: str = "LT"):
        """Update position for symbol (always allowed)."""
        mem = self.get(symbol)
        mem.position_qty = qty
        mem.bucket = bucket
    
    def add_order(self, order: OrderRecord):
        """
        Track a new order (CACHE ONLY).
        
        GUARDED: Raises RuntimeError in OBSERVE_ONLY mode.
        """
        if _OBSERVE_ONLY_MODE:
            raise RuntimeError(
                f"[SYMBOL_MEMORY] OBSERVE_ONLY VIOLATION: "
                f"Attempted to add order {order.order_id} for {order.symbol}. "
                f"Order writes are BLOCKED in OBSERVE_ONLY mode."
            )
        mem = self.get(order.symbol)
        mem.active_orders[order.order_id] = order
    
    def remove_order(self, symbol: str, order_id: str):
        """
        Remove order from tracking.
        
        GUARDED: Raises RuntimeError in OBSERVE_ONLY mode.
        """
        if _OBSERVE_ONLY_MODE:
            raise RuntimeError(
                f"[SYMBOL_MEMORY] OBSERVE_ONLY VIOLATION: "
                f"Attempted to remove order {order_id} for {symbol}. "
                f"Order writes are BLOCKED in OBSERVE_ONLY mode."
            )
        if symbol in self.memories:
            self.memories[symbol].active_orders.pop(order_id, None)
    
    def get_expired_orders(self) -> List[OrderRecord]:
        """Get all expired orders across all symbols (read-only, always allowed)."""
        expired = []
        for mem in self.memories.values():
            for order in mem.active_orders.values():
                if order.is_expired:
                    expired.append(order)
        return expired
    
    def get_stale_symbols(self) -> List[str]:
        """Get symbols with stale truth data (>90s)."""
        return [s for s, m in self.memories.items() if m.last_truth.is_stale]
    
    def get_active_symbols(self) -> List[str]:
        """Get symbols with positions or active orders."""
        return [s for s, m in self.memories.items() 
                if m.position_qty != 0 or m.active_order_count > 0]
    
    def set_excluded(self, symbols: Set[str]):
        """Mark symbols as excluded."""
        for sym, mem in self.memories.items():
            mem.is_excluded = sym in symbols
    
    def flush_csv_snapshot(self, force: bool = False, interval: float = 300.0):
        """
        Write CSV snapshot of all symbol states.
        Called every 5 minutes unless forced.
        """
        now = time.time()
        if not force and (now - self._last_csv_flush) < interval:
            return
        
        self._last_csv_flush = now
        date_str = datetime.now().strftime("%Y%m%d")
        csv_path = self.persist_dir / f"symbol_state_{date_str}.csv"
        
        rows = []
        for mem in self.memories.values():
            rows.append(mem.snapshot())
        
        if not rows:
            return
        
        # Write CSV
        fieldnames = list(rows[0].keys())
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    
    def log_event(self, event_type: str, data: Dict[str, Any]):
        """
        Append event to JSONL log.
        Throttled to avoid spam.
        """
        now = time.time()
        date_str = datetime.now().strftime("%Y%m%d")
        jsonl_path = self.persist_dir / f"runall_events_{date_str}.jsonl"
        
        event = {
            'ts': now,
            'ts_iso': datetime.now().isoformat(),
            'event_type': event_type,
            **data
        }
        
        with open(jsonl_path, 'a') as f:
            f.write(json.dumps(event) + '\n')
    
    def log_observe_action(
        self,
        symbol: str,
        engine: str,
        intent_id: str,
        intent_reason: str,
        order_id: str,
        order_state: str,
        ttl_remaining: float,
        would_cancel: bool,
        would_replace: bool,
        would_submit: bool,
        derisk_state: str,
        notes: str
    ):
        """
        Log OBSERVE_ONLY action with full audit contract.
        
        This is the Phase 1 log format required by ChatGPT.
        """
        date_str = datetime.now().strftime("%Y%m%d")
        jsonl_path = self.persist_dir / f"observe_actions_{date_str}.jsonl"
        
        record = {
            'ts': datetime.now().isoformat(),
            'symbol': symbol,
            'engine': engine,
            'orchestrator_mode': 'OBSERVE_ONLY',
            'intent_id': intent_id,
            'intent_reason': intent_reason,
            'order_id': order_id,
            'order_state': order_state,
            'ttl_remaining': round(ttl_remaining, 1),
            'min_replace_interval': 2.5,
            'would_cancel': would_cancel,
            'would_replace': would_replace,
            'would_submit': would_submit,
            'derisk_state': derisk_state,
            'notes': notes
        }
        
        with open(jsonl_path, 'a') as f:
            f.write(json.dumps(record) + '\n')
    
    def get_summary(self) -> Dict[str, Any]:
        """Get aggregate summary for logging."""
        active = [m for m in self.memories.values() if m.position_qty != 0]
        return {
            'total_symbols': len(self.memories),
            'symbols_with_positions': len(active),
            'stale_count': len(self.get_stale_symbols()),
            'total_active_orders': sum(m.active_order_count for m in self.memories.values()),
            'excluded_count': sum(1 for m in self.memories.values() if m.is_excluded),
            'suppressed_count': sum(1 for m in self.memories.values() if m.is_suppressed),
        }
