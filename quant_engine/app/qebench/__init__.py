"""
QeBench CSV Manager

Manages CSV files for QeBench benchmark tracking:
- qebench_positions.csv: Current position states
- qebench_fills.csv: Fill history
"""
import csv
import os
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from loguru import logger


class QeBenchCSV:
    def __init__(self, account: str = "IBKR_PED", data_dir: str = "data"):
        """
        Initialize QeBench CSV manager for specific account.
        
        Args:
            account: "IBKR_PED", "IBKR_GUN", or "HAMMER_PRO"
            data_dir: Data directory (same as BEFDAY files)
        """
        self.account = account
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Account-specific CSV files (same location as befibped.csv, etc.)
        account_prefix = {
            "IBKR_PED": "ibped",
            "IBKR_GUN": "ibgun",
            "HAMMER_PRO": "hampro"
        }.get(account, "ibped")
        
        self.positions_file = self.data_dir / f"{account_prefix}qebench.csv"
        self.fills_file = self.data_dir / f"{account_prefix}qebench_fills.csv"
        
        logger.info(f"[QeBench] Using files for {account}:")
        logger.info(f"  - Positions: {self.positions_file}")
        logger.info(f"  - Fills: {self.fills_file}")
        
        self._init_csv_files()
    
    # CSV field definitions (v3: PFF benchmark + Time tracking)
    POS_FIELDS = [
        'symbol', 'total_qty', 'weighted_avg_cost',
        'weighted_pff_fill', 'weighted_time_fill', 'last_updated'
    ]
    FILL_FIELDS = [
        'symbol', 'qty', 'fill_price',
        'pff_at_fill', 'fill_timestamp', 'source'
    ]

    def _init_csv_files(self):
        """Initialize CSV files if they don't exist"""
        # Positions CSV
        if not self.positions_file.exists():
            with open(self.positions_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=self.POS_FIELDS)
                writer.writeheader()
            logger.info(f"[QeBench] Created {self.positions_file}")
        else:
            # Migrate: add new columns if missing, remove old ones
            self._migrate_add_column(self.positions_file, self.POS_FIELDS, 'weighted_pff_fill', '0')
            self._migrate_add_column(self.positions_file, self.POS_FIELDS, 'weighted_time_fill', '0')
            self._migrate_remove_column(self.positions_file, 'weighted_bench_fill')
        
        # Fills CSV
        if not self.fills_file.exists():
            with open(self.fills_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=self.FILL_FIELDS)
                writer.writeheader()
            logger.info(f"[QeBench] Created {self.fills_file}")
        else:
            self._migrate_add_column(self.fills_file, self.FILL_FIELDS, 'pff_at_fill', '0')
            self._migrate_remove_column(self.fills_file, 'bench_price_at_fill')

    def _migrate_add_column(self, filepath: Path, target_fields: list, new_col: str, default: str):
        """Add a column to an existing CSV if it's missing (one-time migration)."""
        try:
            with open(filepath, 'r', newline='') as f:
                reader = csv.DictReader(f)
                if new_col in (reader.fieldnames or []):
                    return  # already has the column
                rows = list(reader)
            # Re-write with new column
            for row in rows:
                if new_col not in row:
                    row[new_col] = default
            with open(filepath, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=target_fields, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(rows)
            logger.info(f"[QeBench] Migrated {filepath.name}: added '{new_col}' column")
        except Exception as e:
            logger.warning(f"[QeBench] Migration skipped for {filepath.name}: {e}")
    
    def _migrate_remove_column(self, filepath: Path, old_col: str):
        """Remove an old column from CSV if it exists (one-time migration)."""
        try:
            with open(filepath, 'r', newline='') as f:
                reader = csv.DictReader(f)
                if old_col not in (reader.fieldnames or []):
                    return  # column doesn't exist, nothing to do
                rows = list(reader)
            # Re-write without old column (extrasaction='ignore' handles it)
            new_fields = [c for c in (reader.fieldnames or []) if c != old_col]
            with open(filepath, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=new_fields, extrasaction='ignore')
                writer.writeheader()
                writer.writerows(rows)
            logger.info(f"[QeBench] Migrated {filepath.name}: removed '{old_col}' column")
        except Exception as e:
            logger.warning(f"[QeBench] Column removal skipped for {filepath.name}: {e}")
    
    def update_position(
        self,
        symbol: str,
        total_qty: int,
        weighted_avg_cost: float,
        weighted_pff_fill: float = 0.0,
        weighted_time_fill: float = 0.0,
    ):
        """Update or add position in CSV (PFF benchmark + time tracking)"""
        # Read all positions
        positions = self.get_all_positions()
        position_map = {p['symbol']: p for p in positions}
        
        # Update or add
        position_map[symbol] = {
            'symbol': symbol,
            'total_qty': total_qty,
            'weighted_avg_cost': round(weighted_avg_cost, 4),
            'weighted_pff_fill': round(weighted_pff_fill, 4),
            'weighted_time_fill': round(weighted_time_fill, 2),
            'last_updated': datetime.now().isoformat()
        }
        
        # Write back
        with open(self.positions_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.POS_FIELDS)
            writer.writeheader()
            writer.writerows(position_map.values())
        
        logger.info(
            f"[QeBench] Updated {symbol}: {total_qty}@{weighted_avg_cost:.2f} "
            f"pff@{weighted_pff_fill:.2f} time@{weighted_time_fill:.1f}d"
        )
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        """Get position data for a symbol"""
        positions = self.get_all_positions()
        for pos in positions:
            if pos['symbol'] == symbol:
                return pos
        return None
    
    def get_all_positions(self) -> List[Dict]:
        """Get all positions from CSV"""
        if not self.positions_file.exists():
            return []
        
        positions = []
        with open(self.positions_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Convert numeric fields
                row['total_qty'] = int(float(row['total_qty']))
                row['weighted_avg_cost'] = float(row['weighted_avg_cost'])
                # PFF column (backward compat: default 0 if missing)
                pff_raw = row.get('weighted_pff_fill', '0')
                row['weighted_pff_fill'] = float(pff_raw) if pff_raw else 0.0
                # Time column (backward compat: default 0 if missing)
                time_raw = row.get('weighted_time_fill', '0')
                row['weighted_time_fill'] = float(time_raw) if time_raw else 0.0
                # Legacy: remove old bench_fill if present
                row.pop('weighted_bench_fill', None)
                positions.append(row)
        
        return positions
    
    def add_fill(
        self,
        symbol: str,
        qty: int,
        fill_price: float,
        pff_price: float = 0.0,
        fill_timestamp: str = None,
        source: str = "MANUAL"
    ):
        """Add fill to CSV (PFF benchmark only)"""
        if not fill_timestamp:
            fill_timestamp = datetime.now().isoformat()
        
        with open(self.fills_file, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.FILL_FIELDS)
            writer.writerow({
                'symbol': symbol,
                'qty': qty,
                'fill_price': round(fill_price, 4),
                'pff_at_fill': round(pff_price, 4),
                'fill_timestamp': fill_timestamp,
                'source': source
            })
        
        logger.info(
            f"[QeBench] Added fill: {symbol} {qty}@{fill_price:.2f} "
            f"pff@{pff_price:.2f}"
        )
    
    def get_fills_for_symbol(self, symbol: str) -> List[Dict]:
        """Get all fills for a symbol"""
        if not self.fills_file.exists():
            return []
        
        fills = []
        with open(self.fills_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['symbol'] == symbol:
                    row['qty'] = int(float(row['qty']))
                    row['fill_price'] = float(row['fill_price'])
                    # PFF column (backward compat)
                    pff_raw = row.get('pff_at_fill', '0')
                    row['pff_at_fill'] = float(pff_raw) if pff_raw else 0.0
                    # Legacy: remove old bench column if present
                    row.pop('bench_price_at_fill', None)
                    fills.append(row)
        
        return fills
    
    def reset_position_bench_fill(self, symbol: str, new_pff_fill: float = None, new_time_fill: float = None):
        """Update pff_fill and/or time_fill for reset"""
        positions = self.get_all_positions()
        
        for pos in positions:
            if pos['symbol'] == symbol:
                if new_pff_fill is not None:
                    pos['weighted_pff_fill'] = round(new_pff_fill, 4)
                if new_time_fill is not None:
                    pos['weighted_time_fill'] = round(new_time_fill, 2)
                pos['last_updated'] = datetime.now().isoformat()
                break
        
        # Write back
        with open(self.positions_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.POS_FIELDS, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(positions)
        
        logger.info(f"[QeBench] Reset {symbol} pff@fill: {new_pff_fill}")


# Singleton per account
_csv_instances = {}

def get_qebench_csv(account: str = "IBKR_PED") -> QeBenchCSV:
    """
    Get or create QeBench CSV manager for account.
    
    Args:
        account: "IBKR_PED", "IBKR_GUN", or "HAMMER_PRO"
    """
    global _csv_instances
    if account not in _csv_instances:
        _csv_instances[account] = QeBenchCSV(account=account)
    return _csv_instances[account]

