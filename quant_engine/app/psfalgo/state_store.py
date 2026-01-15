"""
PSFALGO State Store
SQLite-based persistence for daily and 3h tracking windows.
"""

import sqlite3
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from app.core.logger import logger


class PSFALGOStateStore:
    """
    SQLite-based state store for PSFALGO position tracking.
    
    Tracks:
    - Daily net add usage per symbol
    - 3h net change history per symbol
    - Today's average cost for long/short additions
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize state store.
        
        Args:
            db_path: Path to SQLite database. If None, uses data/psfalgo_state.db
        """
        if db_path is None:
            # Default to data/psfalgo_state.db relative to project root
            project_root = Path(__file__).parent.parent.parent
            db_path = project_root / "data" / "psfalgo_state.db"
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self._init_db()
    
    def _init_db(self):
        """Initialize database tables"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # Daily tracker: symbol -> daily net add usage
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS daily_tracker (
                    symbol TEXT NOT NULL,
                    date TEXT NOT NULL,
                    daily_add_used REAL DEFAULT 0.0,
                    daily_add_long_qty REAL DEFAULT 0.0,
                    daily_add_short_qty REAL DEFAULT 0.0,
                    daily_add_long_cost REAL DEFAULT 0.0,
                    daily_add_short_cost REAL DEFAULT 0.0,
                    PRIMARY KEY (symbol, date)
                )
            """)
            
            # 3h change history: symbol -> timestamp -> net qty change
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS change_3h_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    net_qty_change REAL NOT NULL,
                    current_qty REAL NOT NULL
                )
            """)
            
            # Create index separately
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_symbol_timestamp 
                ON change_3h_history (symbol, timestamp)
            """)
            
            # Befday qty storage: symbol -> date -> befday_qty
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS befday_qty_store (
                    symbol TEXT NOT NULL,
                    date TEXT NOT NULL,
                    befday_qty REAL NOT NULL,
                    PRIMARY KEY (symbol, date)
                )
            """)
            
            conn.commit()
            conn.close()
            logger.info(f"PSFALGO state store initialized at {self.db_path}")
            
        except Exception as e:
            logger.error(f"Error initializing PSFALGO state store: {e}", exc_info=True)
            raise
    
    def get_daily_tracker(self, symbol: str, date: Optional[str] = None) -> Dict[str, Any]:
        """
        Get daily tracker for a symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            date: Date string (YYYY-MM-DD). If None, uses today.
            
        Returns:
            Dict with daily_add_used, daily_add_long_qty, daily_add_short_qty, etc.
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT daily_add_used, daily_add_long_qty, daily_add_short_qty,
                       daily_add_long_cost, daily_add_short_cost
                FROM daily_tracker
                WHERE symbol = ? AND date = ?
            """, (symbol, date))
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'daily_add_used': row[0] or 0.0,
                    'daily_add_long_qty': row[1] or 0.0,
                    'daily_add_short_qty': row[2] or 0.0,
                    'daily_add_long_cost': row[3] or 0.0,
                    'daily_add_short_cost': row[4] or 0.0
                }
            else:
                return {
                    'daily_add_used': 0.0,
                    'daily_add_long_qty': 0.0,
                    'daily_add_short_qty': 0.0,
                    'daily_add_long_cost': 0.0,
                    'daily_add_short_cost': 0.0
                }
                
        except Exception as e:
            logger.error(f"Error getting daily tracker for {symbol}: {e}", exc_info=True)
            return {
                'daily_add_used': 0.0,
                'daily_add_long_qty': 0.0,
                'daily_add_short_qty': 0.0,
                'daily_add_long_cost': 0.0,
                'daily_add_short_cost': 0.0
            }
    
    def get_befday_qty(self, symbol: str, date: Optional[str] = None) -> float:
        """
        Get befday_qty for a symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            date: Date string (YYYY-MM-DD). If None, uses today.
            
        Returns:
            befday_qty or 0.0 if not found
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT befday_qty
                FROM befday_qty_store
                WHERE symbol = ? AND date = ?
            """, (symbol, date))
            
            row = cursor.fetchone()
            conn.close()
            
            if row and row[0] is not None:
                return float(row[0])
            else:
                return 0.0
                
        except Exception as e:
            logger.error(f"Error getting befday_qty for {symbol}: {e}", exc_info=True)
            return 0.0
    
    def set_befday_qty(self, symbol: str, befday_qty: float, date: Optional[str] = None):
        """
        Store befday_qty for a symbol (typically called at start of day).
        
        Args:
            symbol: Symbol (PREF_IBKR)
            befday_qty: Before-day quantity
            date: Date string (YYYY-MM-DD). If None, uses today.
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO befday_qty_store (symbol, date, befday_qty)
                VALUES (?, ?, ?)
            """, (symbol, date, befday_qty))
            
            conn.commit()
            conn.close()
            logger.debug(f"Stored befday_qty for {symbol} on {date}: {befday_qty}")
                
        except Exception as e:
            logger.error(f"Error storing befday_qty for {symbol}: {e}", exc_info=True)
    
    def update_daily_tracker(
        self,
        symbol: str,
        net_add: float,
        long_qty: float = 0.0,
        short_qty: float = 0.0,
        long_cost: float = 0.0,
        short_cost: float = 0.0,
        date: Optional[str] = None
    ):
        """
        Update daily tracker for a symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            net_add: Net add quantity (same direction)
            long_qty: Long quantity added today
            short_qty: Short quantity added today
            long_cost: Total cost for long additions
            short_cost: Total cost for short additions
            date: Date string (YYYY-MM-DD). If None, uses today.
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            # Get current values
            cursor.execute("""
                SELECT daily_add_used, daily_add_long_qty, daily_add_short_qty,
                       daily_add_long_cost, daily_add_short_cost
                FROM daily_tracker
                WHERE symbol = ? AND date = ?
            """, (symbol, date))
            
            row = cursor.fetchone()
            
            if row:
                # Update existing
                new_used = (row[0] or 0.0) + abs(net_add)
                new_long_qty = (row[1] or 0.0) + long_qty
                new_short_qty = (row[2] or 0.0) + short_qty
                new_long_cost = (row[3] or 0.0) + long_cost
                new_short_cost = (row[4] or 0.0) + short_cost
                
                cursor.execute("""
                    UPDATE daily_tracker
                    SET daily_add_used = ?, daily_add_long_qty = ?, daily_add_short_qty = ?,
                        daily_add_long_cost = ?, daily_add_short_cost = ?
                    WHERE symbol = ? AND date = ?
                """, (new_used, new_long_qty, new_short_qty, new_long_cost, new_short_cost, symbol, date))
            else:
                # Insert new
                cursor.execute("""
                    INSERT INTO daily_tracker
                    (symbol, date, daily_add_used, daily_add_long_qty, daily_add_short_qty,
                     daily_add_long_cost, daily_add_short_cost)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (symbol, date, abs(net_add), long_qty, short_qty, long_cost, short_cost))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error updating daily tracker for {symbol}: {e}", exc_info=True)
    
    def add_3h_change(self, symbol: str, net_qty_change: float, current_qty: float):
        """
        Add a 3h change record.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            net_qty_change: Net quantity change
            current_qty: Current quantity after change
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            timestamp = datetime.now().isoformat()
            
            cursor.execute("""
                INSERT INTO change_3h_history (symbol, timestamp, net_qty_change, current_qty)
                VALUES (?, ?, ?, ?)
            """, (symbol, timestamp, net_qty_change, current_qty))
            
            # Clean up old records (keep only last 24 hours)
            cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
            cursor.execute("""
                DELETE FROM change_3h_history
                WHERE timestamp < ?
            """, (cutoff,))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error adding 3h change for {symbol}: {e}", exc_info=True)
    
    def get_3h_net_change(self, symbol: str) -> float:
        """
        Get net change over last 3 hours for a symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            
        Returns:
            Net quantity change over last 3 hours
        """
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cutoff = (datetime.now() - timedelta(hours=3)).isoformat()
            
            cursor.execute("""
                SELECT SUM(net_qty_change) as total_change
                FROM change_3h_history
                WHERE symbol = ? AND timestamp >= ?
            """, (symbol, cutoff))
            
            row = cursor.fetchone()
            conn.close()
            
            return row[0] if row[0] is not None else 0.0
            
        except Exception as e:
            logger.error(f"Error getting 3h net change for {symbol}: {e}", exc_info=True)
            return 0.0
    
    def get_todays_avg_cost(self, symbol: str, date: Optional[str] = None) -> Dict[str, float]:
        """
        Get today's average cost for long and short additions.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            date: Date string (YYYY-MM-DD). If None, uses today.
            
        Returns:
            Dict with 'long_avg_cost' and 'short_avg_cost'
        """
        tracker = self.get_daily_tracker(symbol, date)
        
        long_qty = tracker['daily_add_long_qty']
        short_qty = tracker['daily_add_short_qty']
        long_cost = tracker['daily_add_long_cost']
        short_cost = tracker['daily_add_short_cost']
        
        long_avg = long_cost / long_qty if long_qty > 0 else None
        short_avg = short_cost / short_qty if short_qty > 0 else None
        
        return {
            'long_avg_cost': long_avg,
            'short_avg_cost': short_avg
        }

