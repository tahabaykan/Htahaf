"""
PSFALGO Execution Ledger
DRY-RUN ONLY - Records approved actions without broker execution.

This ledger provides a safe intermediate step between preview and real execution.
"""

import sqlite3
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime
from app.core.logger import logger


class PSFALGOExecutionLedger:
    """
    SQLite-based execution ledger for PSFALGO actions.
    
    DRY-RUN ONLY: No broker execution, only records approved actions.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize execution ledger.
        
        Args:
            db_path: Path to SQLite database. If None, uses data/psfalgo_ledger.db
        """
        if db_path is None:
            # Default to data/psfalgo_ledger.db relative to project root
            project_root = Path(__file__).parent.parent.parent
            db_path = project_root / "data" / "psfalgo_ledger.db"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._init_db()
    
    def _init_db(self):
        """Initialize database table"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # Execution ledger table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS execution_ledger (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    cycle_id TEXT,
                    cycle_timestamp TEXT,
                    symbol TEXT NOT NULL,
                    psfalgo_action TEXT NOT NULL,
                    size_percent REAL NOT NULL,
                    size_lot_estimate INTEGER NOT NULL,
                    exposure_mode TEXT,
                    guard_status TEXT,
                    action_reason TEXT,
                    position_snapshot TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes separately
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_symbol_timestamp 
                ON execution_ledger (symbol, timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON execution_ledger (timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cycle_id 
                ON execution_ledger (cycle_id)
            """)
            
            conn.commit()
            conn.close()
            logger.info(f"PSFALGO execution ledger initialized at {self.db_path}")
            
        except Exception as e:
            logger.error(f"Error initializing PSFALGO execution ledger: {e}", exc_info=True)
            raise
    
    def add_entry(
        self,
        symbol: str,
        psfalgo_action: str,
        size_percent: float,
        size_lot_estimate: int,
        exposure_mode: Optional[Dict[str, Any]] = None,
        guard_status: Optional[List[str]] = None,
        action_reason: Optional[str] = None,
        position_snapshot: Optional[Dict[str, Any]] = None,
        cycle_id: Optional[str] = None,
        cycle_timestamp: Optional[str] = None
    ) -> bool:
        """
        Add an entry to the execution ledger.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            psfalgo_action: Action type (REDUCE_LONG, ADD_SHORT, etc.)
            size_percent: Size percentage
            size_lot_estimate: Estimated lot size
            exposure_mode: Exposure mode dict (optional)
            guard_status: Guard status list (optional)
            action_reason: Action reason string (optional)
            position_snapshot: Position snapshot dict (optional)
            
        Returns:
            True if added successfully, False otherwise
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            timestamp = datetime.now().isoformat()
            
            # Serialize complex fields to JSON
            exposure_mode_json = json.dumps(exposure_mode) if exposure_mode else None
            guard_status_json = json.dumps(guard_status) if guard_status else None
            position_snapshot_json = json.dumps(position_snapshot) if position_snapshot else None
            
            cursor.execute("""
                INSERT INTO execution_ledger
                (timestamp, cycle_id, cycle_timestamp, symbol, psfalgo_action, size_percent, size_lot_estimate,
                 exposure_mode, guard_status, action_reason, position_snapshot)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                timestamp,
                cycle_id,
                cycle_timestamp,
                symbol,
                psfalgo_action,
                size_percent,
                size_lot_estimate,
                exposure_mode_json,
                guard_status_json,
                action_reason,
                position_snapshot_json
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"PSFALGO ledger entry added: {symbol} - {psfalgo_action}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding ledger entry for {symbol}: {e}", exc_info=True)
            return False
    
    def get_latest_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get latest ledger entries.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of ledger entry dicts
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT timestamp, cycle_id, cycle_timestamp, symbol, psfalgo_action, size_percent, size_lot_estimate,
                       exposure_mode, guard_status, action_reason, position_snapshot, created_at
                FROM execution_ledger
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))
            
            rows = cursor.fetchall()
            conn.close()
            
            entries = []
            for row in rows:
                # Deserialize JSON fields
                exposure_mode = json.loads(row[7]) if row[7] else None
                guard_status = json.loads(row[8]) if row[8] else None
                position_snapshot = json.loads(row[10]) if row[10] else None
                
                entries.append({
                    'timestamp': row[0],
                    'cycle_id': row[1],
                    'cycle_timestamp': row[2],
                    'symbol': row[3],
                    'psfalgo_action': row[4],
                    'size_percent': row[5],
                    'size_lot_estimate': row[6],
                    'exposure_mode': exposure_mode,
                    'guard_status': guard_status,
                    'action_reason': row[9],
                    'position_snapshot': position_snapshot,
                    'created_at': row[11]
                })
            
            return entries
            
        except Exception as e:
            logger.error(f"Error getting ledger entries: {e}", exc_info=True)
            return []
    
    def get_entries_by_symbol(self, symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get ledger entries for a specific symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            limit: Maximum number of entries to return
            
        Returns:
            List of ledger entry dicts
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT timestamp, cycle_id, cycle_timestamp, symbol, psfalgo_action, size_percent, size_lot_estimate,
                       exposure_mode, guard_status, action_reason, position_snapshot, created_at
                FROM execution_ledger
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (symbol, limit))
            
            rows = cursor.fetchall()
            conn.close()
            
            entries = []
            for row in rows:
                exposure_mode = json.loads(row[7]) if row[7] else None
                guard_status = json.loads(row[8]) if row[8] else None
                position_snapshot = json.loads(row[10]) if row[10] else None
                
                entries.append({
                    'timestamp': row[0],
                    'cycle_id': row[1],
                    'cycle_timestamp': row[2],
                    'symbol': row[3],
                    'psfalgo_action': row[4],
                    'size_percent': row[5],
                    'size_lot_estimate': row[6],
                    'exposure_mode': exposure_mode,
                    'guard_status': guard_status,
                    'action_reason': row[9],
                    'position_snapshot': position_snapshot,
                    'created_at': row[11]
                })
            
            return entries
            
        except Exception as e:
            logger.error(f"Error getting ledger entries for {symbol}: {e}", exc_info=True)
            return []

