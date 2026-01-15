"""
BefDay Snapshot System

Captures daily baseline positions at market open for each account.
Separates overnight positions from intraday trading activity.
"""

import csv
import json
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from app.core.logger import logger
from app.core.redis_client import get_redis_client
from app.event_driven.state.store import StateStore


class BefDaySnapshot:
    """Daily baseline snapshot system"""
    
    # Account IDs
    ACCOUNT_HAMMER = "HAMMER"
    ACCOUNT_IBKR_GUN = "IBKR_GUN"
    ACCOUNT_IBKR_PED = "IBKR_PED"
    
    def __init__(self):
        redis_client = get_redis_client().sync
        if not redis_client:
            raise RuntimeError("Redis client not available")
        
        self.state_store = StateStore(redis_client=redis_client)
        self.befday_key_prefix = "befday"
        
        # CSV file paths (in data directory)
        self.data_dir = Path(__file__).parent.parent.parent.parent / "data"
        self.data_dir.mkdir(exist_ok=True)
    
    def get_csv_path(self, account_id: str) -> Path:
        """Get CSV file path for account"""
        filename_map = {
            self.ACCOUNT_HAMMER: "befham.csv",
            self.ACCOUNT_IBKR_GUN: "befibgun.csv",
            self.ACCOUNT_IBKR_PED: "befibped.csv",
        }
        filename = filename_map.get(account_id, f"bef{account_id.lower()}.csv")
        return self.data_dir / filename
    
    def get_redis_key(self, account_id: str, snapshot_date: date) -> str:
        """Get Redis key for snapshot"""
        date_str = snapshot_date.isoformat()
        return f"{self.befday_key_prefix}:{date_str}:{account_id}"
    
    def has_snapshot_today(self, account_id: str, snapshot_date: Optional[date] = None) -> bool:
        """Check if snapshot exists for today"""
        if snapshot_date is None:
            snapshot_date = date.today()
        
        redis_key = self.get_redis_key(account_id, snapshot_date)
        snapshot = self.state_store.get_state(redis_key)
        return snapshot is not None
    
    def fetch_positions(self, account_id: str) -> List[Dict[str, Any]]:
        """
        Fetch current positions for account (MOCK for now)
        
        Returns:
            List of position dicts with: symbol, quantity, avg_price, notional
        """
        # MOCK: Return mock positions
        # In production, this would fetch from broker API
        mock_positions = {
            self.ACCOUNT_HAMMER: [
                {"symbol": "AAPL", "quantity": 100, "avg_price": 150.0, "notional": 15000.0},
                {"symbol": "MSFT", "quantity": -50, "avg_price": 300.0, "notional": 15000.0},
            ],
            self.ACCOUNT_IBKR_GUN: [
                {"symbol": "GOOGL", "quantity": 200, "avg_price": 100.0, "notional": 20000.0},
            ],
            self.ACCOUNT_IBKR_PED: [
                {"symbol": "TSLA", "quantity": 50, "avg_price": 250.0, "notional": 12500.0},
            ],
        }
        
        return mock_positions.get(account_id, [])
    
    def get_prev_close_price(self, symbol: str) -> float:
        """
        Get previous close price for symbol (MOCK for now)
        
        In production, this would fetch from market data provider
        """
        # MOCK: Return mock prev_close prices
        mock_prices = {
            "AAPL": 150.0,
            "MSFT": 300.0,
            "GOOGL": 100.0,
            "TSLA": 250.0,
        }
        return mock_prices.get(symbol, 100.0)
    
    def create_snapshot(
        self,
        account_id: str,
        snapshot_date: Optional[date] = None,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Create BefDay snapshot for account
        
        Args:
            account_id: Account ID (HAMMER, IBKR_GUN, IBKR_PED)
            snapshot_date: Date for snapshot (default: today)
            force: Force snapshot even if already exists
        
        Returns:
            Snapshot data
        """
        if snapshot_date is None:
            snapshot_date = date.today()
        
        # Check if snapshot already exists (idempotent)
        if not force and self.has_snapshot_today(account_id, snapshot_date):
            logger.info(
                f"⏭️ [{account_id}] Snapshot already exists for {snapshot_date}, skipping"
            )
            return self.load_snapshot(account_id, snapshot_date)
        
        logger.info(f"📸 [{account_id}] Creating BefDay snapshot for {snapshot_date}")
        
        # Fetch positions
        positions = self.fetch_positions(account_id)
        
        # Create snapshot entries
        snapshot_entries = []
        for pos in positions:
            symbol = pos.get("symbol", "UNKNOWN")
            quantity = pos.get("quantity", 0)
            befday_qty = quantity
            prev_close = self.get_prev_close_price(symbol)
            befday_cost = prev_close  # Use prev_close as baseline cost
            
            entry = {
                "symbol": symbol,
                "befday_qty": befday_qty,
                "befday_cost": befday_cost,
                "prev_close": prev_close,
                "notional": abs(befday_qty * befday_cost),
            }
            snapshot_entries.append(entry)
        
        # Create snapshot data
        snapshot_data = {
            "account_id": account_id,
            "snapshot_date": snapshot_date.isoformat(),
            "created_at": datetime.utcnow().isoformat(),
            "entries": snapshot_entries,
            "total_symbols": len(snapshot_entries),
            "total_notional": sum(e["notional"] for e in snapshot_entries),
        }
        
        # Persist to Redis
        redis_key = self.get_redis_key(account_id, snapshot_date)
        self.state_store.set_state(redis_key, snapshot_data)
        
        # Persist to CSV
        self._write_csv(account_id, snapshot_data)
        
        logger.info(
            f"✅ [{account_id}] Snapshot created: {len(snapshot_entries)} symbols, "
            f"total_notional=${snapshot_data['total_notional']:,.2f}"
        )
        
        return snapshot_data
    
    def _write_csv(self, account_id: str, snapshot_data: Dict[str, Any]):
        """Write snapshot to CSV file"""
        csv_path = self.get_csv_path(account_id)
        
        # Check if file exists and has data for this date
        entries = snapshot_data.get("entries", [])
        if not entries:
            return
        
        # Write CSV (append mode, with date column)
        file_exists = csv_path.exists()
        
        with open(csv_path, "a", newline="") as f:
            writer = csv.writer(f)
            
            # Write header if new file
            if not file_exists:
                writer.writerow([
                    "date", "symbol", "befday_qty", "befday_cost", "prev_close", "notional"
                ])
            
            # Write entries
            snapshot_date = snapshot_data.get("snapshot_date", date.today().isoformat())
            for entry in entries:
                writer.writerow([
                    snapshot_date,
                    entry["symbol"],
                    entry["befday_qty"],
                    entry["befday_cost"],
                    entry["prev_close"],
                    entry["notional"],
                ])
        
        logger.debug(f"📝 [{account_id}] Wrote snapshot to CSV: {csv_path}")
    
    def load_snapshot(self, account_id: str, snapshot_date: Optional[date] = None) -> Optional[Dict[str, Any]]:
        """Load snapshot from Redis"""
        if snapshot_date is None:
            snapshot_date = date.today()
        
        redis_key = self.get_redis_key(account_id, snapshot_date)
        snapshot = self.state_store.get_state(redis_key)
        return snapshot
    
    def load_from_csv(self, account_id: str, snapshot_date: Optional[date] = None) -> List[Dict[str, Any]]:
        """Load snapshot entries from CSV for a specific date"""
        if snapshot_date is None:
            snapshot_date = date.today()
        
        csv_path = self.get_csv_path(account_id)
        if not csv_path.exists():
            return []
        
        date_str = snapshot_date.isoformat()
        entries = []
        
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("date") == date_str:
                    entries.append({
                        "symbol": row["symbol"],
                        "befday_qty": int(row["befday_qty"]),
                        "befday_cost": float(row["befday_cost"]),
                        "prev_close": float(row.get("prev_close", row["befday_cost"])),
                        "notional": float(row["notional"]),
                    })
        
        return entries
    
    def get_befday_entry(self, account_id: str, symbol: str, snapshot_date: Optional[date] = None) -> Optional[Dict[str, Any]]:
        """Get BefDay entry for a specific symbol"""
        snapshot = self.load_snapshot(account_id, snapshot_date)
        if not snapshot:
            return None
        
        entries = snapshot.get("entries", [])
        for entry in entries:
            if entry.get("symbol") == symbol:
                return entry
        
        return None



