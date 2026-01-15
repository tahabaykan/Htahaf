"""
Position Snapshot API - Production-Grade

Provides async position snapshot API for PSFALGO decision engines.
Aggregates data from position manager, market data, and static data.
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from app.core.logger import logger
from app.psfalgo.decision_models import PositionSnapshot, PositionPriceStatus
from app.market_data.grouping import resolve_primary_group, resolve_secondary_group

@dataclass
class PositionSnapshotAPI:
    """
    Position Snapshot API - async, production-grade.
    
    Responsibilities:
    - Get position snapshots from position manager
    - Enrich with market data (current price, P&L)
    - Enrich with static data (group, cgrup)
    - Calculate holding time metrics
    - Format for decision engines
    """
    
    def __init__(
        self,
        position_manager=None,
        static_store: Optional[StaticDataStore] = None,
        market_data_cache: Optional[Dict[str, Dict[str, Any]]] = None
    ):
        """
        Initialize Position Snapshot API.
        
        Args:
            position_manager: PositionManager instance
            static_store: StaticDataStore instance
            market_data_cache: Market data cache {symbol: market_data}
        """
        self.position_manager = position_manager
        self.static_store = static_store
        self.market_data_cache = market_data_cache or {}
    
    async def get_position_snapshot(
        self,
        account_id: str = "HAMPRO",
        symbols: Optional[List[str]] = None,
        include_zero_positions: bool = False
    ) -> List[PositionSnapshot]:
        """
        Get position snapshot for symbols within STRICT ACCOUNT SCOPE.
        
        Args:
            account_id: Account ID (HAMPRO, IBKR_PED, IBKR_GUN). REQUIRED.
            symbols: List of symbols to get snapshots for. If None, gets all positions.
            include_zero_positions: Include positions with qty=0 (default: False)
            
        Returns:
            List of PositionSnapshot objects for the specified account.
        """
        try:
            logger.info(f"[POSITION_SNAPSHOT] Fetching for Account: {account_id}")
            
            snapshots = []
            
            # CASE A: IBKR Account
            if account_id in ["IBKR_PED", "IBKR_GUN"]:
                ibkr_positions = await self._get_ibkr_positions(symbols, target_account_type=account_id)
                logger.info(f"[POSITION_SNAPSHOT] {account_id}: fetched {len(ibkr_positions)} positions")
                
                for pos_data in ibkr_positions:
                    snapshot = await self._enrich_position(pos_data, pos_data.get('symbol'), account_id)
                    if snapshot:
                        if not include_zero_positions and abs(snapshot.qty) < 0.01:
                            continue
                        snapshots.append(snapshot)
            
            # CASE B: Hammer Account (HAMPRO)
            elif account_id == "HAMPRO":
                if self.position_manager:
                    hammer_positions = self._get_positions_from_manager(symbols)
                    logger.info(f"[POSITION_SNAPSHOT] HAMPRO: fetched {len(hammer_positions)} positions")
                    
                    for pos_data in hammer_positions:
                         snapshot = await self._enrich_position(pos_data, pos_data.get('symbol'), account_id)
                         if snapshot:
                             if not include_zero_positions and abs(snapshot.qty) < 0.01:
                                 continue
                             snapshots.append(snapshot)
            
            else:
                logger.error(f"[POSITION_SNAPSHOT] Unknown account_id: {account_id}")
                return []
            
            logger.debug(f"[POSITION_SNAPSHOT] Returned {len(snapshots)} positions for {account_id}")
            return snapshots
            
        except Exception as e:
            logger.error(f"Error getting position snapshot: {e}", exc_info=True)
            return []
    
    def _get_positions_from_manager(self, symbols: Optional[List[str]]) -> List[Dict[str, Any]]:
        """
        Get positions from Hammer Position Manager.
        """
        # Adapter for HammerPositionsService (get_positions method)
        if hasattr(self.position_manager, 'get_positions'):
            try:
                raw_positions = self.position_manager.get_positions(force_refresh=False)
                
                positions = []
                for pos in raw_positions:
                    symbol = pos.get('symbol')
                    # Filter by symbols if provided
                    if symbols and symbol not in symbols:
                        continue
                    
                    positions.append({
                        'symbol': symbol,
                        'qty': pos.get('quantity', 0.0),
                        'avg_price': pos.get('avg_price', 0.0),
                        'realized_pnl': 0.0,
                        'unrealized_pnl': pos.get('unrealized_pnl', 0.0),
                        'last_update_time': datetime.now().timestamp()
                    })
                return positions
            except Exception as e:
                logger.error(f"Error getting positions from service: {e}")
                return []

        # Adapter for Legacy Position Manager (dict access)
        if hasattr(self.position_manager, 'positions'):
            positions = []
            for symbol, pos_data in self.position_manager.positions.items():
                if symbols and symbol not in symbols:
                    continue
                
                position_dict = {
                    'symbol': symbol,
                    'qty': pos_data.get('qty', 0.0),
                    'avg_price': pos_data.get('avg_price', 0.0),
                    'realized_pnl': pos_data.get('realized_pnl', 0.0),
                    'unrealized_pnl': pos_data.get('unrealized_pnl', 0.0),
                    'last_update_time': pos_data.get('last_update_time', 0.0)
                }
                positions.append(position_dict)
            return positions
        
        return []

    async def _get_ibkr_positions(
        self, 
        symbols: Optional[List[str]],
        target_account_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get positions from specific IBKR account.
        """
        try:
            from app.psfalgo.ibkr_connector import get_ibkr_connector
            
            # Strict mode: Only check one target account provided by caller
            if not target_account_type:
                 return []

            connector = get_ibkr_connector(account_type=target_account_type)
            
            if connector and connector.is_connected():
                positions = await connector.get_positions()
                result_positions = []
                
                for pos in positions:
                    symbol = pos.get('symbol')
                    if symbols and symbol not in symbols:
                        continue
                    
                    result_positions.append(pos)
                return result_positions
            else:
                return []
            
        except Exception as e:
            logger.error(f"Error getting IBKR positions: {e}", exc_info=True)
            return []
    
    async def _enrich_position(
        self,
        pos_data: Dict[str, Any],
        symbol: str,
        account_id: str
    ) -> Optional[PositionSnapshot]:
        """
        Enrich position data with market data (Price Status Handling).
        """
        try:
            qty = pos_data.get('qty', 0.0)
            avg_price = pos_data.get('avg_price', 0.0)
            last_update_time = pos_data.get('last_update_time', 0.0)
            
            # Symbol Normalization
            normalized_symbol = self.normalize_ibkr_symbol(symbol)
            
            # Get current market price (ALWAYS from HAMMER using NORMALIZED symbol)
            current_price = self._get_current_price(normalized_symbol)
            
            # Fallback to original symbol logic
            if current_price is None:
                current_price = self._get_current_price(symbol)
            
            # PRICE STATUS LOGIC
            price_status = PositionPriceStatus.OK
            
            if current_price is None or current_price <= 0:
                # Missing price behavior: MARK as NO_PRICE but return snapshot (qty visible)
                current_price = 0.0
                price_status = PositionPriceStatus.NO_PRICE
            
            # Calculate unrealized P&L
            unrealized_pnl = (current_price - avg_price) * qty if avg_price > 0 else 0.0
            
            # Get group/cgrup from static data
            group, cgrup = self._get_group_info(symbol)
            
            # Calculate holding time metrics
            position_open_ts, holding_minutes = self._calculate_holding_time(last_update_time)
            
            # PHASE 8: LT/MM Split & Netting Logic
            # -------------------------------------------------------------
            from app.psfalgo.internal_ledger_store import get_internal_ledger_store, initialize_internal_ledger_store
            ledger = get_internal_ledger_store()
            if not ledger:
                initialize_internal_ledger_store()
                ledger = get_internal_ledger_store()
            
            lt_qty_raw = 0.0
            if ledger:
                lt_qty_raw = ledger.get_lt_quantity(account_id, symbol)
            
            mm_qty_raw = qty - lt_qty_raw
            
            # Determine Display Bucket & View Mode
            display_qty = qty
            display_bucket = "MM" # Default assumption
            view_mode = "SINGLE_BUCKET"
            
            # Logic implementation of Phase 8.2 Rules
            is_lt_zero = abs(lt_qty_raw) < 0.0001
            is_mm_zero = abs(mm_qty_raw) < 0.0001
            
            if is_lt_zero and is_mm_zero:
                display_bucket = "FLAT"
            elif is_lt_zero:
                display_bucket = "MM"
                view_mode = "SINGLE_BUCKET"
            elif is_mm_zero:
                display_bucket = "LT"
                view_mode = "SINGLE_BUCKET"
            else:
                # Both exist - check direction
                same_sign = (lt_qty_raw > 0 and mm_qty_raw > 0) or (lt_qty_raw < 0 and mm_qty_raw < 0)
                
                if same_sign:
                    # SAME Sign -> SPLIT (MIXED)
                    display_bucket = "MIXED"
                    view_mode = "SPLIT_SAME_DIR"
                else:
                    # OPPOSITE Sign -> NET (Dominant Bucket)
                    view_mode = "NETTED_OPPOSITE"
                    # Determine dominant bucket by absolute size
                    if abs(lt_qty_raw) >= abs(mm_qty_raw):
                        display_bucket = "LT"
                    else:
                        display_bucket = "MM"

            # Create PositionSnapshot
            snapshot = PositionSnapshot(
                symbol=symbol,
                qty=qty,
                avg_price=avg_price,
                current_price=current_price,
                unrealized_pnl=unrealized_pnl,
                group=group,
                cgrup=cgrup,
                account_type=account_id,
                position_open_ts=position_open_ts,
                holding_minutes=holding_minutes,
                price_status=price_status,
                
                # Phase 8 Fields
                lt_qty_raw=lt_qty_raw,
                mm_qty_raw=mm_qty_raw,
                display_qty=display_qty,
                display_bucket=display_bucket,
                view_mode=view_mode,
                
                timestamp=datetime.now()
            )
            
            return snapshot
            
        except Exception as e:
            logger.error(f"Error enriching position {symbol}: {e}", exc_info=True)
            return None
    
    def _get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current market price for symbol.
        
        Priority:
        1. last (from market_data_cache)
        2. bid (if long position)
        3. ask (if short position)
        4. price (fallback)
        
        Args:
            symbol: Symbol (PREF_IBKR)
            
        Returns:
            Current price or None
        """
        # Dynamic import to ensure we see the LATEST authentic global cache
        # (Avoids stale reference issues if init happened too early)
        from app.api.market_data_routes import market_data_cache
        
        market_data = market_data_cache.get(symbol, {})
        
        # Priority 1: last
        if 'last' in market_data and market_data['last']:
            return float(market_data['last'])
        
        # Priority 2: price (fallback)
        if 'price' in market_data and market_data['price']:
            return float(market_data['price'])
        
        # Priority 3: mid price (bid + ask) / 2
        bid = market_data.get('bid')
        ask = market_data.get('ask')
        if bid and ask and float(bid) > 0 and float(ask) > 0:
            return (float(bid) + float(ask)) / 2.0
        
        # Priority 4: bid or ask (whichever available)
        if bid and float(bid) > 0:
            return float(bid)
        if ask and float(ask) > 0:
            return float(ask)
            
        # Debugging: Why did it fail?
        # Only log if cache seems populated but this symbol is missing/empty
        if len(market_data_cache) > 0:
            if not market_data:
                 logger.debug(f"[PRICE_LOOKUP_FAIL] Symbol '{symbol}' not found in cache (Size: {len(market_data_cache)})")
            else:
                 logger.debug(f"[PRICE_LOOKUP_FAIL] Symbol '{symbol}' found but no valid price keys. Data: {market_data}")
        
        return None
        ask = market_data.get('ask')
        if bid and ask and bid > 0 and ask > 0:
            return (float(bid) + float(ask)) / 2.0
        
        # Priority 4: bid or ask (whichever available)
        if bid and bid > 0:
            return float(bid)
        if ask and ask > 0:
            return float(ask)
        
        return None
    
    def _get_group_info(self, symbol: str) -> tuple[Optional[str], Optional[str]]:
        """
        Get group and cgrup for symbol from static data.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            
        Returns:
            Tuple of (group, cgrup)
        """
        if not self.static_store:
            return None, None
        
        static_data = self.static_store.get_static_data(symbol)
        if not static_data:
            return None, None
        
        # Get primary group
        group = resolve_primary_group(static_data, symbol)
        
        # Get secondary group (CGRUP) if applicable
        cgrup = None
        if group in ['heldkuponlu', 'heldkuponlukreciliz', 'heldkuponlukreorta']:
            cgrup = resolve_secondary_group(static_data, group)
        
        return group, cgrup
    
    def _calculate_holding_time(self, last_update_time: float) -> tuple[Optional[datetime], float]:
        """
        Calculate holding time metrics.
        
        Args:
            last_update_time: Unix timestamp of last position update
            
        Returns:
            Tuple of (position_open_ts, holding_minutes)
        """
        if not last_update_time or last_update_time <= 0:
            return None, 0.0
        
        try:
            # Convert to datetime
            position_open_ts = datetime.fromtimestamp(last_update_time)
            
            # Calculate holding minutes
            now = datetime.now()
            holding_delta = now - position_open_ts
            holding_minutes = holding_delta.total_seconds() / 60.0
            
            return position_open_ts, holding_minutes
            
        except Exception as e:
            logger.debug(f"Error calculating holding time: {e}")
            return None, 0.0

    @staticmethod
    def normalize_ibkr_symbol(symbol: str) -> str:
        """
        Normalize IBKR symbol to match internal FAST/Janall naming convention.
        
        Strict Logic (User Instruction):
        - Replace '-' with ' PR'
        
        Examples:
        - MITT-A -> MITT PRA
        - ACR-D  -> ACR PRD
        - CIM-C  -> CIM PRC
        - PRS    -> PRS (no change)
        
        Args:
            symbol: Original IBKR symbol
            
        Returns:
            Normalized symbol
        """
        if not symbol:
            return ""
        
        # Strict replacement rule: "-" -> " PR"
        return symbol.replace('-', ' PR').strip()


# Global instance
_position_snapshot_api: Optional[PositionSnapshotAPI] = None


def get_position_snapshot_api() -> Optional[PositionSnapshotAPI]:
    """Get global PositionSnapshotAPI instance"""
    return _position_snapshot_api


def initialize_position_snapshot_api(
    position_manager=None,
    static_store: Optional[StaticDataStore] = None,
    market_data_cache: Optional[Dict[str, Dict[str, Any]]] = None
):
    """Initialize global PositionSnapshotAPI instance"""
    global _position_snapshot_api
    _position_snapshot_api = PositionSnapshotAPI(
        position_manager=position_manager,
        static_store=static_store,
        market_data_cache=market_data_cache
    )
    logger.info("PositionSnapshotAPI initialized")

