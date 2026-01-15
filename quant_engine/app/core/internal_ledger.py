"""
Internal Ledger - Persistent Strategy Attribution
=================================================

Tracks the "source" of each position's quantity (LT or MM).
Crucial for preserving strategy attribution across days.

Storage: `data/ledger/{account_id}/internal_ledger.json`

Logic:
1.  **4 Buckets**: LT_LONG, LT_SHORT, MM_LONG, MM_SHORT per symbol.
2.  **Persistence**: Ledger is saved to disk after every update.
3.  **Attribution**: New orders are attributed to LT or MM based on source.
4.  **Netting**: Fills reduce the opposing bucket first (FIFO or Pro-Rata), then same-side bucket.
5.  **Tag Persistence**: Tags remain until position is closed (qty=0).

Phase 11 Update:
- Account-scoped storage.
- Strict 4-bucket model.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict, field
from app.core.logger import logger

@dataclass
class LedgerEntry:
    symbol: str
    lt_long: float = 0.0
    lt_short: float = 0.0
    mm_long: float = 0.0
    mm_short: float = 0.0
    
    @property
    def net_qty(self) -> float:
        return (self.lt_long + self.mm_long) - (self.lt_short + self.mm_short)
        
    @property
    def lt_net(self) -> float:
        return self.lt_long - self.lt_short
        
    @property
    def mm_net(self) -> float:
        return self.mm_long - self.mm_short

class InternalLedgerStore:
    """
    Manages persistent ledger for a specific account.
    """
    
    def __init__(self, account_id: str, data_dir: Path = None):
        self.account_id = account_id
        self.data_dir = data_dir or Path("data/ledger")
        self.file_path = self.data_dir / account_id / "internal_ledger.json"
        
        self.entries: Dict[str, LedgerEntry] = {}
        self._load()
        
    def _load(self):
        """Load from disk."""
        if not self.file_path.exists():
            return
            
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for sym, entry_data in data.items():
                    self.entries[sym] = LedgerEntry(**entry_data)
        except Exception as e:
            logger.error(f"[InternalLedger] Error loading {self.file_path}: {e}")

    def _save(self):
        """Save to disk."""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            data = {sym: asdict(entry) for sym, entry in self.entries.items()}
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"[InternalLedger] Error saving {self.file_path}: {e}")

    def get_entry(self, symbol: str) -> LedgerEntry:
        if symbol not in self.entries:
            self.entries[symbol] = LedgerEntry(symbol=symbol)
        return self.entries[symbol]

    def record_transaction(self, symbol: str, qty: float, source: str):
        """
        Record a fill or transaction.
        qty > 0: BUY/COVER
        qty < 0: SELL/SHORT
        source: 'LT' or 'MM'
        """
        entry = self.get_entry(symbol)
        
        # Simplified Logic (Phase 11):
        # We need to act on specific buckets.
        # BUY (Positive Qty):
        #   1. Reduce SHORTs (Cover) -> First MM Short, then LT Short? Or proportional?
        #      Prompt guidance: "Netting logic... dominant bucket carry".
        #      Let's use specific rule: Cover reduces same-source short first?
        #      Actually, usually trades are intentional. 
        #      If source=LT and Action=BUY (Cover), we expect it to reduce LT_SHORT.
        #      But if LT intent covers MORE than LT_SHORT, does it eat MM_SHORT?
        #      Yes, position is fungible.
        #   2. If no shorts left, Increase LONGs -> LT_LONG or MM_LONG based on source.
        
        # SELL (Negative Qty):
        #   1. Reduce LONGs (Sell) -> Reduce LT_LONG or MM_LONG.
        #   2. If no longs left, Increase SHORTs.
        
        remaining = qty
        
        # Handling BUY (Positive)
        if qty > 0:
            # 1. Cover Shorts
            # Priority: If source is LT, cover LT Shorts first. If MM, cover MM Shorts first.
            if source == 'LT':
                cover_lt = min(entry.lt_short, remaining)
                entry.lt_short -= cover_lt
                remaining -= cover_lt
                
                cover_mm = min(entry.mm_short, remaining)
                entry.mm_short -= cover_mm
                remaining -= cover_mm
            else: # MM
                cover_mm = min(entry.mm_short, remaining)
                entry.mm_short -= cover_mm
                remaining -= cover_mm
                
                cover_lt = min(entry.lt_short, remaining)
                entry.lt_short -= cover_lt
                remaining -= cover_lt
            
            # 2. Open Longs (if any remaining)
            if remaining > 0:
                if source == 'LT':
                    entry.lt_long += remaining
                else:
                    entry.mm_long += remaining
                    
        # Handling SELL (Negative)
        else:
            remaining = abs(qty) # Work with positive magnitude
            
            # 1. Sell Longs
            if source == 'LT':
                sell_lt = min(entry.lt_long, remaining)
                entry.lt_long -= sell_lt
                remaining -= sell_lt
                
                sell_mm = min(entry.mm_long, remaining)
                entry.mm_long -= sell_mm
                remaining -= sell_mm
            else: # MM
                sell_mm = min(entry.mm_long, remaining)
                entry.mm_long -= sell_mm
                remaining -= sell_mm
                
                sell_lt = min(entry.lt_long, remaining)
                entry.lt_long -= sell_lt
                remaining -= sell_lt
                
            # 2. Open Shorts (if any remaining)
            if remaining > 0:
                if source == 'LT':
                    entry.lt_short += remaining
                else:
                    entry.mm_short += remaining

        # Cleanup zero entries? Maybe keep for day history? 
        # For now, save.
        self._save()

# Global Manager
_ledger_stores: Dict[str, InternalLedgerStore] = {}

def get_internal_ledger_store(account_id: str) -> InternalLedgerStore:
    if account_id not in _ledger_stores:
        _ledger_stores[account_id] = InternalLedgerStore(account_id)
    return _ledger_stores[account_id]
