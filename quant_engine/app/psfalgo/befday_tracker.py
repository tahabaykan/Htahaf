"""
BEFDAY Tracker - Janall-Compatible

Tracks daily position snapshots at market open (Before Day).

Janall Logic:
- befham.csv: Hammer Pro pozisyonları (HAMPRO modu)
- befibgun.csv: IBKR GUN pozisyonları
- befibped.csv: IBKR PED pozisyonları
- Günde 1 kez, 00:00-16:30 arası çalışır
- Mevcut dosya bugünün tarihine sahipse tekrar çalışmaz

Purpose:
- Günün başındaki pozisyon snapshot'ını kaydet
- Gün içi değişiklikleri takip et
- PnL ve performans hesaplamaları için referans noktası
"""

import os
import json
import asyncio
import pandas as pd
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from app.core.logger import logger


@dataclass
class BefDayConfig:
    """BEFDAY Tracker configuration"""
    enabled: bool = True
    
    # CSV dosya adları
    csv_file_hampro: str = "befham.csv"
    csv_file_ibkr_gun: str = "befibgun.csv"
    csv_file_ibkr_ped: str = "befibped.csv"
    
    # Çalışma penceresi (yerel saat)
    window_start_hour: int = 0
    window_start_minute: int = 0
    window_end_hour: int = 23
    window_end_minute: int = 59
    
    # JSON snapshot dosyası
    snapshot_file: str = "befday_snapshot.json"
    
    # Çıktı dizini (varsayılan: proje kök dizini)
    output_dir: Optional[str] = None


@dataclass
class PositionSnapshot:
    """Single position snapshot"""
    symbol: str
    quantity: float
    avg_cost: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float
    position_type: str  # LONG, SHORT, FLAT
    export_time: str
    book: str = "MM"  # POS TAG: MM (default, migration) or LT
    pos_tag: str = "MM"  # POS TAG explicit: MM or LT (synced with book)
    account: str = ""
    exchange: str = ""
    last_price: float = 0.0
    cost_basis: float = 0.0


class BefDayTracker:
    """
    BEFDAY Tracker - Daily position snapshot manager.
    
    Janall'daki befham.csv, befibgun.csv, befibped.csv mantığını implement eder.
    
    Features:
    - Günlük pozisyon snapshot'ı (market open öncesi)
    - Mod bazlı CSV dosyaları (HAMPRO, IBKR_GUN, IBKR_PED)
    - Otomatik günlük kontrol (00:00-16:30)
    - JSON snapshot geçmişi
    """
    
    def __init__(self, config: Optional[BefDayConfig] = None):
        """
        Initialize BEFDAY Tracker.
        
        Args:
            config: BefDayConfig object
        """
        self.config = config or BefDayConfig()
        
        # Output directory
        if self.config.output_dir:
            self.output_dir = Path(self.config.output_dir)
        else:
            # Default: StockTracker root dir (C:\StockTracker)
            # app/psfalgo/befday_tracker.py -> app/psfalgo -> app -> quant_engine -> StockTracker
            self.output_dir = Path(__file__).parent.parent.parent.parent
        
        # Tracking state
        self._checked_today: Dict[str, bool] = {
            'hampro': False,
            'ibkr_gun': False,
            'ibkr_ped': False
        }
        self._last_check_date: Optional[date] = None
        
        # Snapshot history
        self._snapshots: Dict[str, Dict[str, Any]] = {}
        self._load_snapshots()
        
        logger.info(
            f"BefDayTracker initialized: output_dir={self.output_dir}, "
            f"window={self.config.window_start_hour:02d}:{self.config.window_start_minute:02d}-"
            f"{self.config.window_end_hour:02d}:{self.config.window_end_minute:02d}"
        )
    
    def _load_snapshots(self):
        """Load snapshot history from JSON file"""
        try:
            snapshot_path = self.output_dir / self.config.snapshot_file
            if snapshot_path.exists():
                with open(snapshot_path, 'r', encoding='utf-8') as f:
                    self._snapshots = json.load(f)
                logger.debug(f"Loaded {len(self._snapshots)} snapshot days")
        except Exception as e:
            logger.error(f"Error loading snapshots: {e}")
            self._snapshots = {}
    
    def _save_snapshots(self):
        """Save snapshot history to JSON file"""
        try:
            snapshot_path = self.output_dir / self.config.snapshot_file
            with open(snapshot_path, 'w', encoding='utf-8') as f:
                json.dump(self._snapshots, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.error(f"Error saving snapshots: {e}")
    
    def _is_in_window(self) -> bool:
        """Check if current time is within the tracking window"""
        now = datetime.now()
        
        window_start = now.replace(
            hour=self.config.window_start_hour,
            minute=self.config.window_start_minute,
            second=0,
            microsecond=0
        )
        window_end = now.replace(
            hour=self.config.window_end_hour,
            minute=self.config.window_end_minute,
            second=0,
            microsecond=0
        )
        
        return window_start <= now <= window_end
    
    def _reset_daily_flags(self):
        """Reset daily flags if date has changed"""
        today = date.today()
        
        if self._last_check_date != today:
            self._checked_today = {
                'hampro': False,
                'ibkr_gun': False,
                'ibkr_ped': False
            }
            self._last_check_date = today
            logger.debug(f"Daily flags reset for {today}")
    
    def _get_csv_path(self, mode: str) -> Path:
        """Get CSV file path for mode"""
        if mode == 'hampro':
            return self.output_dir / self.config.csv_file_hampro
        elif mode == 'ibkr_gun':
            return self.output_dir / self.config.csv_file_ibkr_gun
        elif mode == 'ibkr_ped':
            return self.output_dir / self.config.csv_file_ibkr_ped
        else:
            return self.output_dir / f"bef{mode}.csv"
    
    def _is_csv_current(self, csv_path: Path) -> bool:
        """Check if CSV file is from today AND has valid column format"""
        if not csv_path.exists():
            return False
        
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(csv_path))
            if mtime.date() != date.today():
                return False
            
            # Also validate column format — reject CSVs with wrong (lowercase) headers
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                header = f.readline().strip()
                if 'Symbol' not in header or 'Quantity' not in header:
                    logger.warning(f"[BEFDAY] CSV {csv_path.name} has invalid columns, will regenerate")
                    return False
            
            return True
        except Exception:
            return False
    
    def should_track(self, mode: str = 'hampro') -> tuple[bool, str]:
        """
        Check if BEFDAY tracking should run.
        
        Args:
            mode: 'hampro', 'ibkr_gun', or 'ibkr_ped'
            
        Returns:
            (should_track, reason)
        """
        if not self.config.enabled:
            return False, "BEFDAY tracking disabled"
        
        # Reset flags if new day
        self._reset_daily_flags()
        
        # Check time window
        if not self._is_in_window():
            return False, f"Outside tracking window ({self.config.window_end_hour:02d}:{self.config.window_end_minute:02d})"
        
        # Check if already tracked today
        if self._checked_today.get(mode, False):
            return False, f"Already tracked today for {mode}"
        
        # Check if CSV is current
        csv_path = self._get_csv_path(mode)
        if self._is_csv_current(csv_path):
            self._checked_today[mode] = True
            return False, f"CSV already exists for today: {csv_path.name}"
        
        return True, f"Ready to track for {mode}"
    
    async def track_positions(
        self,
        positions: List[Dict[str, Any]],
        mode: str = 'hampro',
        account: str = ''
    ) -> bool:
        """
        Track positions and create BEFDAY CSV.
        
        Args:
            positions: List of position dictionaries
            mode: 'hampro', 'ibkr_gun', or 'ibkr_ped'
            account: Account identifier
            
        Returns:
            True if successful
        """
        should_track, reason = self.should_track(mode)
        
        if not should_track:
            logger.info(f"[BEFDAY] Skipping: {reason}")
            return False
        
        try:
            if not positions:
                logger.warning(f"[BEFDAY] No positions to track for {mode}")
                return False
            
            logger.info(f"[BEFDAY] Tracking {len(positions)} positions for {mode}")
            
            # Convert positions to snapshots
            snapshots = []
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            for pos in positions:
                # Parse position data (flexible for different sources)
                symbol = pos.get('symbol', pos.get('Symbol', ''))
                qty = pos.get('qty', pos.get('quantity', pos.get('Quantity', 0)))
                avg_cost = pos.get('avg_cost', pos.get('avg_price', pos.get('AveragePrice', 0)))
                market_value = pos.get('market_value', pos.get('MarketValue', 0))
                unrealized_pnl = pos.get('unrealized_pnl', pos.get('UnrealizedPnL', 0))
                realized_pnl = pos.get('realized_pnl', pos.get('RealizedPnL', 0))
                last_price = pos.get('last_price', pos.get('LastPrice', pos.get('current_price', 0)))
                exchange = pos.get('exchange', pos.get('Exchange', ''))
                
                # Determine position type; normalize qty so short is ALWAYS negative (never positive)
                try:
                    qty = float(qty)
                except (TypeError, ValueError):
                    qty = 0.0
                if qty > 0:
                    position_type = "LONG"
                elif qty < 0:
                    position_type = "SHORT"
                    qty = -abs(qty)  # enforce short quantity is always negative
                else:
                    position_type = "FLAT"
                # Also respect explicit Side/Position_Type from source (e.g. IBKR can send Short with positive qty)
                side_in = (pos.get('side') or pos.get('Side') or '').strip().lower()
                pos_type_in = (pos.get('position_type') or pos.get('Position_Type') or '').strip().upper()
                if side_in == 'short' or pos_type_in == 'SHORT':
                    position_type = "SHORT"
                    qty = -abs(float(qty)) if qty else -0.0
                
                # Calculate market value if not provided
                if not market_value and avg_cost:
                    market_value = abs(qty) * avg_cost
                
                # Get book type (LT or MM)
                # Priority 1: PositionTagStore (Redis — real-time POS TAG)
                book = None
                try:
                    from app.psfalgo.position_tag_store import get_position_tag_store
                    store = get_position_tag_store()
                    if store:
                        redis_tag = store.get_tag(symbol, mode)
                        if redis_tag in ('LT', 'MM'):
                            book = redis_tag
                except Exception:
                    pass
                
                # Priority 2: Input data
                if not book:
                    book = pos.get('book', pos.get('Book'))
                
                # Priority 3: ShadowPositionStore (Ledger history)
                if not book:
                    try:
                        from app.psfalgo.shadow_position_store import ShadowPositionStore
                        shadow_store = ShadowPositionStore()
                        shadow_pos = shadow_store.get_position(symbol)
                        if shadow_pos:
                            book = shadow_pos.get('book')
                    except Exception as e:
                        logger.warning(f"Failed to lookup book for {symbol}: {e}")
                
                # Default to MM if still not found (migration default)
                if book not in ['LT', 'MM']:
                    book = 'MM'
                
                # Store signed quantity: long > 0, short < 0 (BEFDAY ile current/potential aynı işaret olmalı)
                snapshot = PositionSnapshot(
                    symbol=symbol,
                    quantity=float(qty),
                    avg_cost=avg_cost,
                    market_value=market_value,
                    unrealized_pnl=unrealized_pnl,
                    realized_pnl=realized_pnl,
                    position_type=position_type,
                    export_time=current_time,
                    book=book,
                    pos_tag=book,  # POS TAG = book (MM or LT)
                    account=account,
                    exchange=exchange,
                    last_price=last_price,
                    cost_basis=avg_cost
                )
                snapshots.append(snapshot)
            
            # Create CSV
            csv_path = self._get_csv_path(mode)
            success = self._create_csv(snapshots, csv_path)
            
            if success:
                # Save to JSON snapshot
                self._save_daily_snapshot(snapshots, mode)
                
                # Mark as checked
                self._checked_today[mode] = True
                
                # === NEW: Update PositionTagManager with BEFDAY positions ===
                try:
                    from app.psfalgo.position_tags import get_position_tag_manager
                    tag_manager = get_position_tag_manager()
                    for snap in snapshots:
                        is_mm = snap.book == 'MM'
                        qty = snap.quantity if snap.position_type == 'LONG' else -snap.quantity
                        tag_manager.update_on_befday_load(snap.symbol, qty, is_mm)
                    logger.info(f"[BEFDAY] PositionTagManager updated with {len(snapshots)} positions")
                except Exception as tag_e:
                    logger.warning(f"[BEFDAY] Could not update PositionTagManager: {tag_e}")
                # === END NEW ===
                
                # === NEW: Sync POS TAGs to PositionTagStore (Redis) ===
                try:
                    from app.psfalgo.position_tag_store import get_position_tag_store
                    store = get_position_tag_store()
                    if store:
                        befday_positions = [
                            {'symbol': snap.symbol, 'pos_tag': snap.pos_tag}
                            for snap in snapshots
                            if snap.quantity != 0
                        ]
                        store.initialize_from_befday(befday_positions, account_id=mode)
                        logger.info(f"[BEFDAY] PositionTagStore synced with {len(befday_positions)} POS TAGs for {mode}")
                except Exception as store_e:
                    logger.warning(f"[BEFDAY] Could not sync PositionTagStore: {store_e}")
                # === END POS TAG SYNC ===
                
                logger.info(f"[BEFDAY] ✅ {len(snapshots)} positions saved to {csv_path.name}")
                
                # === AUTO MinMax Area CSV (both accounts) ===
                try:
                    from app.psfalgo.minmax_area_service import get_minmax_area_service
                    minmax_svc = get_minmax_area_service()
                    
                    # Build pos/befday maps from snapshots for current account
                    pos_map = {}
                    befday_map = {}
                    for snap in snapshots:
                        pos_map[snap.symbol] = float(snap.quantity) if snap.position_type == 'LONG' else -float(snap.quantity)
                        befday_map[snap.symbol] = pos_map[snap.symbol]
                    
                    # Save MinMax for current account
                    count = minmax_svc.save_to_csv(
                        mode,
                        positions_override=pos_map,
                        befday_override=befday_map,
                    )
                    logger.info(f"[BEFDAY] MinMax Area CSV saved for {mode}: {count} symbols")
                    
                    # Also compute for the OTHER account
                    other_accounts = [a for a in ["HAMPRO", "IBKR_PED"] if a != mode]
                    for other_acc in other_accounts:
                        try:
                            other_count = minmax_svc.save_to_csv(other_acc)
                            logger.info(f"[BEFDAY] MinMax Area CSV saved for {other_acc}: {other_count} symbols")
                        except Exception as other_e:
                            logger.warning(f"[BEFDAY] MinMax Area for {other_acc} failed: {other_e}")
                except Exception as mm_e:
                    logger.warning(f"[BEFDAY] MinMax Area auto-save failed: {mm_e}")
                # === END AUTO MinMax ===
                
                return True
            else:
                return False
            
        except Exception as e:
            logger.error(f"[BEFDAY] Error tracking positions: {e}", exc_info=True)
            return False
    
    def _create_csv(self, snapshots: List[PositionSnapshot], csv_path: Path) -> bool:
        """Create CSV file from snapshots"""
        try:
            data = []
            for snap in snapshots:
                # Calculate 8-Type Taxonomy
                # Origin is always OV for Befday files
                origin = "OV"
                side = "Long" if snap.quantity > 0 else "Short"
                if snap.position_type == "SHORT": side = "Short" # Double check
                
                full_taxonomy = f"{snap.book} {origin} {side}"
                # Short quantity MUST always be written as negative in BEFDAY (never positive)
                qty_out = float(snap.quantity)
                if snap.position_type == "SHORT" and qty_out > 0:
                    qty_out = -qty_out
                
                data.append({
                    'Export_Time': snap.export_time,
                    'Symbol': snap.symbol,
                    'Book': snap.book,
                    'Pos_Tag': snap.pos_tag,  # NEW: POS TAG (MM or LT)
                    'Strategy': snap.book, # Explicit Strategy column
                    'Origin': origin,      # Explicit Origin column
                    'Side': side,          # Explicit Side column
                    'Full_Taxonomy': full_taxonomy, # The requested 8-type tag
                    'Position_Type': snap.position_type,
                    'Quantity': qty_out,
                    'Avg_Cost': snap.avg_cost,
                    'Market_Value': snap.market_value,
                    'Unrealized_PnL': snap.unrealized_pnl,
                    'Realized_PnL': snap.realized_pnl,
                    'Cost_Basis': snap.cost_basis,
                    'Last_Price': snap.last_price,
                    'Exchange': snap.exchange,
                    'Account': snap.account,
                    'Total_Value': snap.market_value + snap.unrealized_pnl
                })
            
            df = pd.DataFrame(data)
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            
            return True
            
        except Exception as e:
            logger.error(f"[BEFDAY] CSV creation error: {e}")
            return False
    
    def _save_daily_snapshot(self, snapshots: List[PositionSnapshot], mode: str):
        """Save daily snapshot to JSON history"""
        try:
            today_str = date.today().strftime('%Y-%m-%d')
            
            if today_str not in self._snapshots:
                self._snapshots[today_str] = {}
            
            self._snapshots[today_str][mode] = {
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'positions_count': len(snapshots),
                'total_value': sum(s.market_value + s.unrealized_pnl for s in snapshots),
                'positions': [
                    {
                        'symbol': s.symbol,
                        'book': s.book,
                        'pos_tag': s.pos_tag,
                        'quantity': s.quantity,
                        'avg_cost': s.avg_cost,
                        'position_type': s.position_type
                    }
                    for s in snapshots
                ]
            }
            
            self._save_snapshots()
            
        except Exception as e:
            logger.error(f"[BEFDAY] Snapshot save error: {e}")
    
    def get_today_snapshot(self, mode: str = 'hampro') -> Optional[Dict[str, Any]]:
        """Get today's snapshot for a mode"""
        today_str = date.today().strftime('%Y-%m-%d')
        return self._snapshots.get(today_str, {}).get(mode)
    
    def get_snapshot_by_date(self, snapshot_date: date, mode: str = 'hampro') -> Optional[Dict[str, Any]]:
        """Get snapshot for a specific date"""
        date_str = snapshot_date.strftime('%Y-%m-%d')
        return self._snapshots.get(date_str, {}).get(mode)
    
    def get_position_change(self, symbol: str, mode: str = 'hampro') -> Dict[str, Any]:
        """
        Get position change from BEFDAY snapshot.
        
        Returns:
            {
                'befday_qty': quantity at start of day,
                'current_qty': current quantity (if available),
                'change': quantity change,
                'befday_avg_cost': avg cost at start of day
            }
        """
        today_snapshot = self.get_today_snapshot(mode)
        
        if not today_snapshot:
            return {
                'befday_qty': 0,
                'current_qty': 0,
                'change': 0,
                'befday_avg_cost': 0,
                'has_befday': False
            }
        
        # Find position in snapshot (quantity is stored signed: long > 0, short < 0)
        for pos in today_snapshot.get('positions', []):
            if pos['symbol'] == symbol:
                befday_qty = float(pos['quantity'])
                return {
                    'befday_qty': befday_qty,
                    'current_qty': 0,  # To be filled by caller
                    'change': 0,  # To be calculated by caller
                    'befday_avg_cost': pos['avg_cost'],
                    'has_befday': True
                }
        
        return {
            'befday_qty': 0,
            'current_qty': 0,
            'change': 0,
            'befday_avg_cost': 0,
            'has_befday': False
        }
    
    def get_all_befday_positions(self, mode: str = 'hampro') -> List[Dict[str, Any]]:
        """Get all positions from today's BEFDAY snapshot"""
        today_snapshot = self.get_today_snapshot(mode)
        
        if not today_snapshot:
            return []
        
        return today_snapshot.get('positions', [])
    
    def get_lt_positions(self, mode: str = 'hampro') -> List[Dict[str, Any]]:
        """Get only LT (Long Term) positions from today's BEFDAY snapshot"""
        all_positions = self.get_all_befday_positions(mode)
        return [p for p in all_positions if p.get('book', 'LT') == 'LT']
    
    def get_mm_positions(self, mode: str = 'hampro') -> List[Dict[str, Any]]:
        """Get only MM (Market Making) positions from today's BEFDAY snapshot"""
        all_positions = self.get_all_befday_positions(mode)
        return [p for p in all_positions if p.get('book') == 'MM']
    
    def get_exposure_by_book(self, mode: str = 'hampro') -> Dict[str, Dict[str, float]]:
        """
        Get exposure summary by book (LT vs MM).
        
        Returns:
            {
                'LT': {'long_qty': X, 'short_qty': Y, 'net_qty': Z},
                'MM': {'long_qty': X, 'short_qty': Y, 'net_qty': Z}
            }
        """
        all_positions = self.get_all_befday_positions(mode)
        
        result = {
            'LT': {'long_qty': 0, 'short_qty': 0, 'net_qty': 0},
            'MM': {'long_qty': 0, 'short_qty': 0, 'net_qty': 0}
        }
        
        for pos in all_positions:
            book = pos.get('book', 'LT')
            qty = pos.get('quantity', 0)
            pos_type = pos.get('position_type', 'FLAT')
            
            if book in result:
                # quantity is signed: long > 0, short < 0
                if pos_type == 'LONG':
                    result[book]['long_qty'] += qty
                    result[book]['net_qty'] += qty
                elif pos_type == 'SHORT':
                    result[book]['short_qty'] += abs(qty)
                    result[book]['net_qty'] += qty  # qty < 0, so net decreases
        
        return result
    
    def get_status(self) -> Dict[str, Any]:
        """Get tracker status"""
        return {
            'enabled': self.config.enabled,
            'output_dir': str(self.output_dir),
            'checked_today': self._checked_today,
            'in_window': self._is_in_window(),
            'window': f"{self.config.window_start_hour:02d}:{self.config.window_start_minute:02d}-"
                      f"{self.config.window_end_hour:02d}:{self.config.window_end_minute:02d}",
            'today_snapshots': {
                mode: self.get_today_snapshot(mode) is not None
                for mode in ['hampro', 'ibkr_gun', 'ibkr_ped']
            }
        }


# ============================================================================
# Global Instance Management
# ============================================================================

_befday_tracker: Optional[BefDayTracker] = None


def get_befday_tracker() -> Optional[BefDayTracker]:
    """Get global BefDayTracker instance"""
    return _befday_tracker


def initialize_befday_tracker(config: Optional[Dict[str, Any]] = None) -> BefDayTracker:
    """Initialize global BefDayTracker instance"""
    global _befday_tracker
    
    if config:
        bef_config = BefDayConfig(
            enabled=config.get('enabled', True),
            csv_file_hampro=config.get('csv_file', config.get('csv_file_hampro', 'befham.csv')),
            csv_file_ibkr_gun=config.get('csv_file_ibkr_gun', 'befibgun.csv'),
            csv_file_ibkr_ped=config.get('csv_file_ibkr_ped', 'befibped.csv'),
            window_start_hour=config.get('window_start_hour', 0),
            window_start_minute=config.get('window_start_minute', 0),
            window_end_hour=config.get('window_end_hour', 16),
            window_end_minute=config.get('window_end_minute', 30),
            snapshot_file=config.get('snapshot_file', 'befday_snapshot.json'),
            output_dir=config.get('output_dir')
        )
    else:
        bef_config = BefDayConfig()
    
    _befday_tracker = BefDayTracker(config=bef_config)
    logger.info("BefDayTracker initialized (Janall-compatible)")
    return _befday_tracker


# ============================================================================
# Convenience Functions
# ============================================================================

async def track_befday_positions(
    positions: List[Dict[str, Any]],
    mode: str = 'hampro',
    account: str = ''
) -> bool:
    """
    Convenience function to track BEFDAY positions.
    
    Args:
        positions: List of position dictionaries
        mode: 'hampro', 'ibkr_gun', or 'ibkr_ped'
        account: Account identifier
        
    Returns:
        True if successful
    """
    tracker = get_befday_tracker()
    if not tracker:
        initialize_befday_tracker()
        tracker = get_befday_tracker()
    
    if not tracker:
        logger.error("[BEFDAY] Tracker not available")
        return False
    
    return await tracker.track_positions(positions, mode, account)


def get_befday_position_change(symbol: str, mode: str = 'hampro') -> Dict[str, Any]:
    """
    Get position change from BEFDAY.
    
    Args:
        symbol: Symbol string
        mode: 'hampro', 'ibkr_gun', or 'ibkr_ped'
        
    Returns:
        Position change info
    """
    tracker = get_befday_tracker()
    if not tracker:
        return {'befday_qty': 0, 'current_qty': 0, 'change': 0, 'has_befday': False}
    
    return tracker.get_position_change(symbol, mode)



