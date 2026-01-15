"""
Market Snapshot Store - Daily Snapshot Management

Manages daily snapshots (befday_* fields) and current market snapshots.
Janall-compatible daily snapshot logic.

Key Principles:
- Market open öncesi: befday_* alanları hesapla
- Gün içinde: befday_* SABİT, live data güncellenir
- Account type separation (IBKR_GUN / IBKR_PED)
"""

from datetime import datetime, date
from typing import Dict, Any, Optional, List
from pathlib import Path
import json

from app.core.logger import logger
from app.psfalgo.market_snapshot_models import MarketSnapshot
from app.market_data.trading_calendar import TradingCalendar


class MarketSnapshotStore:
    """
    Market Snapshot Store - manages daily snapshots and current snapshots.
    
    Responsibilities:
    - Daily snapshot creation (befday_* fields)
    - Current snapshot management
    - Account type separation
    - Snapshot persistence (optional CSV export)
    
    Does NOT:
    - Make trading decisions
    - Execute orders
    """
    
    def __init__(self, snapshot_dir: Optional[Path] = None):
        """
        Initialize Market Snapshot Store.
        
        Args:
            snapshot_dir: Directory for snapshot persistence (optional)
        """
        self.snapshot_dir = snapshot_dir or Path('quant_engine/snapshots')
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        self.trading_calendar = TradingCalendar()
        
        # Current snapshots: {account_type: {symbol: MarketSnapshot}}
        self.current_snapshots: Dict[str, Dict[str, MarketSnapshot]] = {
            'IBKR_GUN': {},
            'IBKR_PED': {}
        }
        
        # Daily snapshots (befday_*): {date: {account_type: {symbol: MarketSnapshot}}}
        self.daily_snapshots: Dict[str, Dict[str, Dict[str, MarketSnapshot]]] = {}
        
        # Current date
        self.current_date: Optional[str] = None
        
        logger.info(f"MarketSnapshotStore initialized (snapshot_dir={self.snapshot_dir})")
    
    def get_current_date(self) -> str:
        """Get current date (YYYY-MM-DD)"""
        return datetime.now().strftime('%Y-%m-%d')
    
    def should_create_daily_snapshot(self) -> bool:
        """
        Check if daily snapshot should be created.
        
        Daily snapshot is created:
        - Before market open (e.g., 16:30 TR = 09:30 ET previous day)
        - On first access of new trading day
        """
        current_date = self.get_current_date()
        
        # If date changed, need new snapshot
        if current_date != self.current_date:
            return True
        
        # If no snapshots for current date, need snapshot
        if current_date not in self.daily_snapshots:
            return True
        
        return False
    
    async def create_daily_snapshot(
        self,
        account_type: str,
        positions: Dict[str, Dict[str, Any]]
    ) -> Dict[str, MarketSnapshot]:
        """
        Create daily snapshot (befday_* fields) for account type.
        
        Args:
            account_type: "IBKR_GUN" or "IBKR_PED"
            positions: {symbol: {qty, cost, ...}} - positions at previous day close
            
        Returns:
            Dict of MarketSnapshots with befday_* fields populated
        """
        current_date = self.get_current_date()
        
        # Initialize daily snapshot for this date if not exists
        if current_date not in self.daily_snapshots:
            self.daily_snapshots[current_date] = {
                'IBKR_GUN': {},
                'IBKR_PED': {}
            }
        
        snapshots: Dict[str, MarketSnapshot] = {}
        
        for symbol, position in positions.items():
            # Create snapshot with befday_* fields
            snapshot = MarketSnapshot(
                symbol=symbol,
                befday_qty=position.get('qty', 0.0),
                befday_cost=position.get('cost', 0.0),
                account_type=account_type,
                snapshot_ts=datetime.now()
            )
            
            snapshots[symbol] = snapshot
        
        # Store daily snapshot
        self.daily_snapshots[current_date][account_type] = snapshots
        self.current_date = current_date
        
        logger.info(
            f"[SNAPSHOT] Created daily snapshot for {account_type} on {current_date}: "
            f"{len(snapshots)} symbols"
        )
        
        # Optional: Persist to file
        await self._persist_daily_snapshot(current_date, account_type, snapshots)
        
        return snapshots
    
    async def update_current_snapshot(
        self,
        symbol: str,
        snapshot: MarketSnapshot,
        account_type: str = 'IBKR_GUN'
    ):
        """
        Update current snapshot for symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            snapshot: MarketSnapshot to store
            account_type: "IBKR_GUN" or "IBKR_PED"
        """
        # Get befday_* from daily snapshot if available
        current_date = self.get_current_date()
        if current_date in self.daily_snapshots:
            daily_snapshot = self.daily_snapshots[current_date].get(account_type, {}).get(symbol)
            if daily_snapshot:
                snapshot.befday_qty = daily_snapshot.befday_qty
                snapshot.befday_cost = daily_snapshot.befday_cost
        
        # Update current snapshot
        if account_type not in self.current_snapshots:
            self.current_snapshots[account_type] = {}
        
        snapshot.account_type = account_type
        self.current_snapshots[account_type][symbol] = snapshot
        
        logger.debug(f"[SNAPSHOT] Updated current snapshot: {symbol} ({account_type})")
    
    def get_current_snapshot(
        self,
        symbol: str,
        account_type: str = 'IBKR_GUN'
    ) -> Optional[MarketSnapshot]:
        """Get current snapshot for symbol"""
        return self.current_snapshots.get(account_type, {}).get(symbol)
    
    def get_all_current_snapshots(
        self,
        account_type: Optional[str] = None
    ) -> Dict[str, MarketSnapshot]:
        """
        Get all current snapshots.
        
        Args:
            account_type: Filter by account type (None = all)
            
        Returns:
            Dict of {symbol: MarketSnapshot}
        """
        if account_type:
            return self.current_snapshots.get(account_type, {}).copy()
        else:
            # Merge all account types
            all_snapshots = {}
            for account_type_snapshots in self.current_snapshots.values():
                all_snapshots.update(account_type_snapshots)
            return all_snapshots
    
    async def _persist_daily_snapshot(
        self,
        date_str: str,
        account_type: str,
        snapshots: Dict[str, MarketSnapshot]
    ):
        """Persist daily snapshot to file (optional)"""
        try:
            snapshot_file = self.snapshot_dir / f"snapshot_{date_str}_{account_type}.json"
            
            snapshot_data = {
                'date': date_str,
                'account_type': account_type,
                'snapshots': {symbol: s.to_dict() for symbol, s in snapshots.items()}
            }
            
            with open(snapshot_file, 'w') as f:
                json.dump(snapshot_data, f, indent=2)
            
            logger.debug(f"[SNAPSHOT] Persisted daily snapshot: {snapshot_file}")
        except Exception as e:
            logger.warning(f"[SNAPSHOT] Error persisting daily snapshot: {e}")


# Global instance
_market_snapshot_store: Optional[MarketSnapshotStore] = None


def get_market_snapshot_store() -> Optional[MarketSnapshotStore]:
    """Get global MarketSnapshotStore instance"""
    return _market_snapshot_store


def initialize_market_snapshot_store(snapshot_dir: Optional[Path] = None):
    """Initialize global MarketSnapshotStore instance"""
    global _market_snapshot_store
    _market_snapshot_store = MarketSnapshotStore(snapshot_dir=snapshot_dir)
    logger.info("MarketSnapshotStore initialized")






