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
    
    def _init_csv_files(self):
        """Initialize CSV files if they don't exist"""
        # Positions CSV
        if not self.positions_file.exists():
            with open(self.positions_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'symbol', 'total_qty', 'weighted_avg_cost', 
                    'weighted_bench_fill', 'last_updated'
                ])
                writer.writeheader()
            logger.info(f"[QeBench] Created {self.positions_file}")
        
        # Fills CSV
        if not self.fills_file.exists():
            with open(self.fills_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'symbol', 'qty', 'fill_price', 'bench_price_at_fill',
                    'fill_timestamp', 'source'
                ])
                writer.writeheader()
            logger.info(f"[QeBench] Created {self.fills_file}")
    
    def update_position(
        self,
        symbol: str,
        total_qty: int,
        weighted_avg_cost: float,
        weighted_bench_fill: float
    ):
        """Update or add position in CSV"""
        # Read all positions
        positions = self.get_all_positions()
        position_map = {p['symbol']: p for p in positions}
        
        # Update or add
        position_map[symbol] = {
            'symbol': symbol,
            'total_qty': total_qty,
            'weighted_avg_cost': round(weighted_avg_cost, 4),
            'weighted_bench_fill': round(weighted_bench_fill, 4),
            'last_updated': datetime.now().isoformat()
        }
        
        # Write back
        with open(self.positions_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'symbol', 'total_qty', 'weighted_avg_cost',
                'weighted_bench_fill', 'last_updated'
            ])
            writer.writeheader()
            writer.writerows(position_map.values())
        
        logger.info(f"[QeBench] Updated {symbol}: {total_qty}@{weighted_avg_cost:.2f} bench@{weighted_bench_fill:.2f}")
    
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
                row['total_qty'] = int(row['total_qty'])
                row['weighted_avg_cost'] = float(row['weighted_avg_cost'])
                row['weighted_bench_fill'] = float(row['weighted_bench_fill'])
                positions.append(row)
        
        return positions
    
    def add_fill(
        self,
        symbol: str,
        qty: int,
        fill_price: float,
        bench_price: float,
        fill_timestamp: str = None,
        source: str = "MANUAL"
    ):
        """Add fill to CSV"""
        if not fill_timestamp:
            fill_timestamp = datetime.now().isoformat()
        
        with open(self.fills_file, 'a', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'symbol', 'qty', 'fill_price', 'bench_price_at_fill',
                'fill_timestamp', 'source'
            ])
            writer.writerow({
                'symbol': symbol,
                'qty': qty,
                'fill_price': round(fill_price, 4),
                'bench_price_at_fill': round(bench_price, 4),
                'fill_timestamp': fill_timestamp,
                'source': source
            })
        
        logger.info(f"[QeBench] Added fill: {symbol} {qty}@{fill_price:.2f} bench@{bench_price:.2f}")
    
    def get_fills_for_symbol(self, symbol: str) -> List[Dict]:
        """Get all fills for a symbol"""
        if not self.fills_file.exists():
            return []
        
        fills = []
        with open(self.fills_file, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['symbol'] == symbol:
                    row['qty'] = int(row['qty'])
                    row['fill_price'] = float(row['fill_price'])
                    row['bench_price_at_fill'] = float(row['bench_price_at_fill'])
                    fills.append(row)
        
        return fills
    
    def reset_position_bench_fill(self, symbol: str, new_bench_fill: float):
        """Update bench_fill for reset-all"""
        positions = self.get_all_positions()
        
        for pos in positions:
            if pos['symbol'] == symbol:
                pos['weighted_bench_fill'] = round(new_bench_fill, 4)
                pos['last_updated'] = datetime.now().isoformat()
                break
        
        # Write back
        with open(self.positions_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'symbol', 'total_qty', 'weighted_avg_cost',
                'weighted_bench_fill', 'last_updated'
            ])
            writer.writeheader()
            writer.writerows(positions)
        
        logger.info(f"[QeBench] Reset {symbol} bench@fill: {new_bench_fill:.2f}")


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

