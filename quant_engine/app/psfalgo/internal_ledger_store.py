"""
Internal Ledger Store - Production-Grade

Manages the persistent state of Long-Term (LT) positions vs Market-Making (MM) positions.
Strictly partitioned by `account_id`.

Path: data/ledger/{account_id}/internal_ledger.json
"""

import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List
from threading import Lock
from datetime import datetime

from app.core.logger import logger

class InternalLedgerStore:
    """
    Internal Ledger Store - Thread-safe access to internal position ledger.
    
    Responsibilities:
    - Track "Pure LT" quantity (lt_qty_raw) persistenly.
    - Persist to disk: data/ledger/{account_id}/internal_ledger.json
    - Provide EOD normalization logic (finalize_day).
    
    Note: "MM Quantity" is DERIVED (Broker Net - LT Raw). We only store LT Raw.
    """
    
    def __init__(self, data_dir: str = "data/ledger"):
        self.data_dir = Path(data_dir)
        self.ledgers: Dict[str, Dict[str, float]] = {}  # {account_id: {symbol: lt_qty}}
        self.locks: Dict[str, Lock] = {}
        self._ensure_dir()
        
    def _ensure_dir(self):
        """Ensure data directory exists"""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
    def _get_lock(self, account_id: str) -> Lock:
        """Get lock for specific account"""
        if account_id not in self.locks:
            self.locks[account_id] = Lock()
        return self.locks[account_id]
    
    def _get_ledger_path(self, account_id: str) -> Path:
        """Get file path for account ledger"""
        # Ensure account specific folder exists
        account_dir = self.data_dir / account_id
        account_dir.mkdir(parents=True, exist_ok=True)
        return account_dir / "internal_ledger.json"
    
    def load_ledger(self, account_id: str):
        """Load ledger for account from disk"""
        with self._get_lock(account_id):
            path = self._get_ledger_path(account_id)
            if path.exists():
                try:
                    with open(path, 'r') as f:
                        data = json.load(f)
                        self.ledgers[account_id] = data.get('lt_positions', {})
                        logger.info(f"[LEDGER] Loaded ledger for {account_id} ({len(self.ledgers[account_id])} symbols)")
                except Exception as e:
                    logger.error(f"[LEDGER] Failed to load ledger for {account_id}: {e}")
                    self.ledgers[account_id] = {}
            else:
                self.ledgers[account_id] = {}
    
    def save_ledger(self, account_id: str):
        """Save ledger for account to disk"""
        with self._get_lock(account_id):
            path = self._get_ledger_path(account_id)
            try:
                data = {
                    'account_id': account_id,
                    'last_updated': datetime.now().isoformat(),
                    'lt_positions': self.ledgers.get(account_id, {})
                }
                with open(path, 'w') as f:
                    json.dump(data, f, indent=2)
                # logger.debug(f"[LEDGER] Saved ledger for {account_id}")
            except Exception as e:
                logger.error(f"[LEDGER] Failed to save ledger for {account_id}: {e}")

    def get_lt_quantity(self, account_id: str, symbol: str) -> float:
        """Get Raw LT quantity for symbol"""
        if account_id not in self.ledgers:
            self.load_ledger(account_id)
            
        return self.ledgers.get(account_id, {}).get(symbol, 0.0)

    def set_lt_quantity(self, account_id: str, symbol: str, qty: float):
        """Set Raw LT quantity (Absoulte set, e.g. from UI override or EOD)"""
        if account_id not in self.ledgers:
            self.load_ledger(account_id)
            
        with self._get_lock(account_id):
            if qty == 0:
                if symbol in self.ledgers[account_id]:
                    del self.ledgers[account_id][symbol]
            else:
                self.ledgers[account_id][symbol] = qty
            
        self.save_ledger(account_id)
        
    def add_lt_trade(self, account_id: str, symbol: str, qty_delta: float):
        """Apply a trade delta to LT quantity"""
        if qty_delta == 0:
            return

        current_qty = self.get_lt_quantity(account_id, symbol)
        new_qty = current_qty + qty_delta
        
        # Rounding protection
        if abs(new_qty) < 0.0001:
            new_qty = 0.0
            
        self.set_lt_quantity(account_id, symbol, new_qty)
        logger.info(f"[LEDGER] {account_id} {symbol}: LT Qty {current_qty} -> {new_qty} (Delta: {qty_delta})")

    def finalize_day(self, account_id: str, broker_positions: Dict[str, float]):
        """
        EOD Normalization Logic.
        
        Logic:
        1. For each symbol in broker positions:
           - Get lt_qty_raw.
           - Calculate mm_qty_raw = broker_net - lt_qty_raw.
           - Rule: "OPPOSITE Sign: Collapse".
             - If LT and MM have opposite signs (one +, one -):
               - We do NOT want to carry this overnight. 
               - Collapse implies we adjust LT so MM becomes 0?
               - Or we adjust so that the net position is fully attributed to the dominant bucket?
             - Implementation Plan says: "Collapse into dominant bucket for next-day carry."
             - This means if Net is +500 (LT +800, MM -300), we act as if we have LT +500, MM 0.
               - So we set LT = Net.
             
           - Rule: "SAME DISPLA Y" (Split Same Dir).
             - If LT +500, MM +100. Net is +600.
             - Plan says: "Keep MIXED" for display but what about overnight carry?
             - Usually we want to keep them separate.
             - So we do NOTHING if same sign.
        
        2. Clean up symbols not in broker_positions (force LT=0 if pos closed).
        
        Args:
            account_id: Account ID
            broker_positions: Dict {symbol: net_qty} from broker/snapshot
        """
        logger.info(f"[LEDGER] Finalizing day for {account_id}...")
        
        if account_id not in self.ledgers:
            self.load_ledger(account_id)
            
        repo = self.ledgers.get(account_id, {})
        all_symbols = set(list(repo.keys()) + list(broker_positions.keys()))
        
        changes_made = False
        
        for symbol in all_symbols:
            broker_net = broker_positions.get(symbol, 0.0)
            lt_raw = repo.get(symbol, 0.0)
            mm_raw = broker_net - lt_raw
            
            # Check for OPPOSITE signs (Netting Logic for Carry)
            is_opposite = (lt_raw > 0 and mm_raw < 0) or (lt_raw < 0 and mm_raw > 0)
            
            if is_opposite:
                logger.info(f"[EOD] {symbol}: Collapsing OPPOSITE buckets (Net {broker_net}, LT {lt_raw}, MM {mm_raw}) -> LT {broker_net}")
                # Collapse all into LT (Assignment to dominant? Or just assign Net to LT?)
                # If we assign Net to LT, then MM = Net - Net = 0.
                # This effectively "realizes" the hedge/arb internal PnL and leaves a directional position.
                repo[symbol] = broker_net
                changes_made = True
            
            # Cleanup zero positions
            if abs(broker_net) < 0.0001 and abs(lt_raw) < 0.0001:
                if symbol in repo:
                    del repo[symbol]
                    changes_made = True
            
            # Safety: If Broker Net is 0, LT must be 0 (cannot hold ghost LT)
            if abs(broker_net) < 0.0001 and abs(lt_raw) > 0.0001:
                 logger.warning(f"[EOD] {symbol}: Broker pos is 0 but LT is {lt_raw}. Forcing LT=0.")
                 if symbol in repo:
                     del repo[symbol]
                     changes_made = True
                     
        if changes_made:
            self.save_ledger(account_id)
            logger.info(f"[LEDGER] Finalize day complete for {account_id}. Ledger updated.")
        else:
            logger.info(f"[LEDGER] Finalize day complete for {account_id}. No changes.")

# Global instance
_internal_ledger_store: Optional[InternalLedgerStore] = None

def get_internal_ledger_store() -> Optional[InternalLedgerStore]:
    """Get global InternalLedgerStore instance"""
    return _internal_ledger_store

def initialize_internal_ledger_store(data_dir: str = "data/ledger"):
    """Initialize global InternalLedgerStore instance"""
    global _internal_ledger_store
    _internal_ledger_store = InternalLedgerStore(data_dir=data_dir)
    logger.info(f"InternalLedgerStore initialized (dir={data_dir})")
