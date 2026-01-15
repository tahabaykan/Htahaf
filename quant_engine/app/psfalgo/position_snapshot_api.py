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
from app.psfalgo.decision_models import PositionSnapshot, PositionPriceStatus, PositionTag
from app.market_data.grouping import resolve_primary_group, resolve_secondary_group
from app.market_data.static_data_store import StaticDataStore

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
            open_qty_map: Dict[str, float] = {}
            
            # Load Befday Map for Taxonomy
            befday_map = self._load_befday_map(account_id)
            logger.info(f"[POSITION_SNAPSHOT] Loaded {len(befday_map)} entries from Befday for {account_id}")

            # CASE A: IBKR Account
            if account_id in ["IBKR_PED", "IBKR_GUN"]:
                from app.psfalgo.ibkr_connector import get_ibkr_connector
                connector = get_ibkr_connector(account_type=account_id)
                
                # Fetch positions
                ibkr_positions = []
                if connector and connector.is_connected():
                    ibkr_positions = await connector.get_positions()
                    # Also fetch open orders for Potential Qty
                    try:
                        open_orders = await connector.get_open_orders()
                        for order in open_orders:
                            sym = order.get('symbol')
                            qty = order.get('totalQuantity', 0)
                            action = order.get('action', 'BUY')
                            if action == 'SELL':
                                qty = -qty
                            if sym:
                                open_qty_map[sym] = open_qty_map.get(sym, 0.0) + qty
                    except Exception as oe:
                         logger.warning(f"Error fetching IBKR open orders: {oe}")

                logger.info(f"[POSITION_SNAPSHOT] {account_id}: fetched {len(ibkr_positions)} positions")
                
                for pos_data in ibkr_positions:
                    sym = pos_data.get('symbol')
                    net_open = open_qty_map.get(sym, 0.0)
                    
                    # Resolve Befday Qty (Try raw symbol and normalized)
                    bef_data = befday_map.get(sym, {})
                    bef_qty = bef_data.get('quantity', 0.0)
                    
                    if sym == 'HOVNP' or sym == 'WRB PRF':
                         logger.info(f"[BEFDAY_DEBUG] Checking {sym}: Found={bool(bef_data)}, Qty={bef_qty}, MapSize={len(befday_map)}")
                    
                    snapshot = await self._enrich_position(pos_data, sym, account_id, net_open_qty=net_open, befday_qty=bef_qty, befday_data=bef_data)
                    if snapshot:
                        if not include_zero_positions and abs(snapshot.qty) < 0.01:
                            continue
                        snapshots.append(snapshot)
            
            # CASE B: Hammer Account (HAMPRO)
            elif account_id == "HAMPRO":
                # Fetch Open Orders via HammerOrdersService
                try:
                    from app.api.trading_routes import get_hammer_orders_service
                    orders_service = get_hammer_orders_service()
                    if orders_service:
                         # Use list_orders or get_orders depending on API
                         all_orders = orders_service.get_orders(force_refresh=False)
                         for order in all_orders:
                             if order.get('status') in ['OPEN', 'PENDING', 'PARTIAL']:
                                 sym = order.get('symbol')
                                 qty = order.get('quantity', 0) - order.get('filled_quantity', 0)
                                 side = order.get('side', 'BUY')
                                 if side == 'SELL':
                                     qty = -qty
                                 if sym:
                                     open_qty_map[sym] = open_qty_map.get(sym, 0.0) + qty
                except Exception as oe:
                    logger.warning(f"Error fetching Hammer open orders: {oe}")

                if self.position_manager:
                    hammer_positions = self._get_positions_from_manager(symbols)
                    logger.info(f"[POSITION_SNAPSHOT] HAMPRO: fetched {len(hammer_positions)} positions")
                    
                    for pos_data in hammer_positions:
                         sym = pos_data.get('symbol')
                         net_open = open_qty_map.get(sym, 0.0)
                         # Resolve Befday Qty
                         bef_data = befday_map.get(sym, {})
                         bef_qty = bef_data.get('quantity', 0.0)
                         
                         snapshot = await self._enrich_position(pos_data, sym, account_id, net_open_qty=net_open, befday_qty=bef_qty, befday_data=bef_data)
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
        account_id: str,
        net_open_qty: float = 0.0,
        befday_qty: float = 0.0,
        befday_data: Optional[Dict[str, Any]] = None
    ) -> Optional[PositionSnapshot]:
        """
        Enrich position data with market data (Price Status Handling).
        """
        try:
            qty = pos_data.get('qty', 0.0)
            avg_price = pos_data.get('avg_price', 0.0)
            last_update_time = pos_data.get('last_update_time', 0.0)
            
            # Taxonomy Determination (Phase 9)
            if befday_data and befday_data.get('full_taxonomy'):
                strategy_type = befday_data.get('strategy', 'LT')
                origin_type = befday_data.get('origin', 'OV')
                full_taxonomy = befday_data.get('full_taxonomy')
            else:
                strategy_type, origin_type, full_taxonomy = self._determine_taxonomy(qty, befday_qty)
            
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
            
            # Determine Base LT from Befday (Default Assumption)
            # Strategy Type determined in Phase 9 above
            bef_lt_base = 0.0
            if strategy_type == "LT":
                 bef_lt_base = befday_qty
            
            lt_qty_raw = 0.0
            if ledger:
                 if ledger.has_symbol(account_id, symbol):
                      lt_qty_raw = ledger.get_lt_quantity(account_id, symbol)
                 else:
                      lt_qty_raw = bef_lt_base
            else:
                 lt_qty_raw = bef_lt_base
            
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

            # Get Previous Close for Intraday PnL
            prev_close = self._get_prev_close(normalized_symbol)
            if prev_close <= 0:
                 prev_close = self._get_prev_close(symbol)
                 
            # Intraday Calculations
            intraday_pnl = 0.0
            intraday_cost = 0.0
            
            if current_price and current_price > 0 and prev_close and prev_close > 0:
                # User heuristic: "Last - PrevClose * Qty" (Simple View)
                intraday_cost = prev_close 
                intraday_pnl = (current_price - prev_close) * qty
            
            # PRICE STATUS LOGIC
            price_status = "OK" 
            
            if current_price is None or current_price <= 0:
                price_status = "NO_PRICE"
            
            # Phase 10: Position Tags (OV/INT Breakdown)
            # -------------------------------------------------------------
            position_tags = self._calculate_position_tags(
                account_id=account_id,
                symbol=symbol,
                befday_qty=befday_qty,
                current_qty=qty,
                befday_data=befday_data
            )
            
            # Determine Dominant Tag for Display (User Requirement: "Cogunluk etkisi")
            # Scan position_tags for largest absolute qty
            dominant_tag = None
            max_tag_qty = -1.0
            
            for tag, t_qty in position_tags.items():
                 if t_qty > max_tag_qty:
                      max_tag_qty = t_qty
                      dominant_tag = tag
            
            # If we found a dominant tag, update taxonomy fields
            if dominant_tag:
                 # format: "BOOK_SIDE_ORIGIN" (e.g. "LT_LONG_OV")
                 parts = dominant_tag.split('_')
                 if len(parts) >= 3:
                      # Update Strategy and Origin based on Dominant
                      strategy_type = parts[0] # LT or MM
                      origin_type = parts[2]   # OV or INT
                      side_str = "Long" if "LONG" in parts[1] else "Short"
                      
                      # Full Taxonomy for Main Display (e.g. "LT OV Long")
                      full_taxonomy = f"{strategy_type} {origin_type} {side_str}"
            
            # Create PositionSnapshot
            snapshot = PositionSnapshot(
                symbol=symbol,
                qty=qty,
                avg_price=avg_price,
                current_price=current_price or 0.0,
                unrealized_pnl=unrealized_pnl,
                group=group,
                cgrup=cgrup,
                account_type=account_id,
                position_open_ts=last_update_time,
                holding_minutes=0.0, 
                price_status=price_status,
                
                # Phase 8 Fields
                lt_qty_raw=lt_qty_raw,
                mm_qty_raw=mm_qty_raw,
                display_qty=qty, 
                display_bucket="MM", 
                view_mode="SINGLE_BUCKET",
                
                # Phase 9: 8-Type Taxonomy (Strict Classification)
                strategy_type=strategy_type,
                origin_type=origin_type,
                full_taxonomy=full_taxonomy,
                befday_qty=befday_qty,
                
                # Phase 10: Position Tags
                position_tags=position_tags,
                
                # Intraday P&L
                prev_close=prev_close,
                intraday_cost=intraday_cost,
                intraday_pnl=intraday_pnl,
                
                potential_qty=qty + net_open_qty,
                timestamp=datetime.now()
            )
            
            return snapshot
            
        except Exception as e:
            logger.error(f"Error enriching position {symbol}: {e}", exc_info=True)
            return None

    def _load_befday_map(self, account_id: str) -> Dict[str, Dict[str, Any]]:
        """
        Load Befday CSV for the given account.
        Returns map: Symbol -> {
            'quantity': float,
            'full_taxonomy': str,
            'strategy': str,
            'origin': str,
            'side': str
        }
        """
        import pandas as pd
        from pathlib import Path
        import os
        
        # Determine filename
        filename = "befday.csv"
        # Map account to filename logic (align with befday_tracker)
        acc_up = account_id.upper()
        if acc_up == "IBKR_PED": 
             filename = "befibped.csv"
        elif acc_up == "IBKR_GUN":
             filename = "befibgun.csv"
        elif acc_up == "HAMPRO":
             filename = "befham.csv"
             
        # Robust Path Logic: Use file location to find root (StockTracker)
        # app/psfalgo/position_snapshot_api.py -> psfalgo -> app -> quant_engine -> StockTracker
        try:
            current_file = Path(__file__).resolve()
            root_dir = current_file.parent.parent.parent.parent
            csv_path = root_dir / filename
            
            # Fallback to CWD if file not found logic fails or verified
            if not csv_path.exists():
                logger.debug(f"[_load_befday_map] Not found at {csv_path}, trying CWD...")
                csv_path = Path(os.getcwd()) / filename
        except Exception:
             csv_path = Path(os.getcwd()) / filename

        if not csv_path.exists():
            logger.warning(f"[_load_befday_map] Befday file not found: {csv_path}")
            return {}
            
        try:
            df = pd.read_csv(csv_path)
            result = {}
            
            # Check required columns
            if 'Symbol' not in df.columns or 'Quantity' not in df.columns:
                logger.error(f"[_load_befday_map] Invalid columns in {filename}: {df.columns}")
                return {}
                
            for _, row in df.iterrows():
                try:
                    sym = str(row['Symbol']).strip() # Strip whitespace!
                    qty = float(row['Quantity'])
                
                    # Extract taxonomy info if available
                    full_tax = str(row.get('Full_Taxonomy', ''))
                    strategy = str(row.get('Strategy', 'LT'))
                    origin = str(row.get('Origin', 'OV'))
                    side = str(row.get('Side', ''))
                    
                    result[sym] = {
                        'quantity': qty,
                        'full_taxonomy': full_tax,
                        'strategy': strategy,
                        'origin': origin,
                        'side': side
                    }
                except Exception as row_error:
                    logger.warning(f"[_load_befday_map] Error parsing row in {filename}: {row_error}")
                    continue

                
            return result
        except Exception as e:
            logger.warning(f"Failed to load {filename}: {e}")
            return {}

    def _determine_taxonomy(self, qty: float, befday_qty: float) -> tuple[str, str, str]:
        """
        Determine Strategy, Origin, and Full Taxonomy string.
        Logic:
        - Origin: If in Befday (befday_qty != 0) -> OV (Overnight). Else INT (Intraday).
        - Strategy: Default LT (Start Assumption).
        - Side: Long/Short based on Qty sign.
        """
        # Origin
        # Note: If befday_qty exists, it's OV.
        # Edge case: If we closed it today (qty=0), it was OV. 
        # But here we are enriching a snapshot with Qty != 0 usually, or Qty=0.
        origin_type = "OV" if abs(befday_qty) > 0.001 else "INT"
        
        # Strategy (Default LT for now as requested)
        # TODO: Check MM history if available
        strategy_type = "LT"
        
        # Side
        side = "Long" if qty >= 0 else "Short"
        if qty == 0 and abs(befday_qty) > 0:
             # Closed position check side of befday
             side = "Long" if befday_qty >= 0 else "Short"
        
        full_taxonomy = f"{strategy_type} {origin_type} {side}"
        return strategy_type, origin_type, full_taxonomy
    
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
        
    def _calculate_position_tags(
        self,
        account_id: str,
        symbol: str,
        befday_qty: float,
        current_qty: float,
        befday_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, float]:
        """
        Calculate 8-Type Position Tags (OV/INT Split).
        
        Logic (User Defined):
        - OV: Based on Befday Quantity + Befday Strategy (LT/MM).
        - INT: Logic requires LT/MM Split of Intraday moves.
             We use InternalLedgerStore (which tracks Total LT) to derive this.
             Total LT = Ledger.get_lt_quantity()
             Total MM = Current - Total LT
             
        - LT_INT = Total LT - LT_OV (adjusted for closure)
        - MM_INT = Total MM - MM_OV (adjusted for closure)
        
        Returns:
            Dict[tag, qty] e.g. {'LT_LONG_OV': 1000.0, 'LT_LONG_INT': 400.0}
        """
        tags: Dict[str, float] = {}
        
        # 0. Get Befday Strategy (Default to LT if not specified)
        bef_strategy = "LT"
        if befday_data:
             st = befday_data.get('strategy', 'LT')
             if str(st).strip() != "": bef_strategy = str(st).strip().upper()
        
        # 1. Fetch Total LT from Internal Ledger
        from app.psfalgo.internal_ledger_store import get_internal_ledger_store, initialize_internal_ledger_store
        store = get_internal_ledger_store()
        if not store:
             initialize_internal_ledger_store()
             store = get_internal_ledger_store()
             
        total_lt = 0.0
        
        # Determine Base LT from Befday (Default Assumption)
        bef_lt_base = 0.0
        if bef_strategy == "LT":
             bef_lt_base = befday_qty
        
        # Check Ledger Overrides
        if store:
             if store.has_symbol(account_id, symbol):
                  # Ledger has explicit state (even if 0) -> Use it
                  total_lt = store.get_lt_quantity(account_id, symbol)
             else:
                  # Ledger has NO state -> Default to Befday Base
                  total_lt = bef_lt_base
        else:
             # No store -> Default to Befday Base
             total_lt = bef_lt_base
             
        # 2. Calculate Total MM
        total_mm = current_qty - total_lt
        
        # 3. Determine Breakdown (OV vs INT) using DailyFillsStore
        # ------------------------------------------------------------------
        # Logic:
        # Use INT components from Daily Fills Log (Actual Filled Orders).
        # Calculate OV as residual (Total - INT).
        
        lt_int_qty = 0.0
        mm_int_qty = 0.0
        
        try:
             from app.trading.daily_fills_store import get_daily_fills_store
             daily_store = get_daily_fills_store()
             breakdown = daily_store.get_intraday_breakdown(account_id, symbol)
             lt_int_qty = breakdown.get('LT', 0.0)
             mm_int_qty = breakdown.get('MM', 0.0)
        except Exception as e:
             # Fallback (Safety)
             pass
             
        # 4. Calculate OV (Residual)
        lt_ov_qty = total_lt - lt_int_qty
        mm_ov_qty = total_mm - mm_int_qty
        
        # 5. Map to Tags
        tags: Dict[PositionTag, float] = {}
        
        def add_tag(qty, book, origin):
             if abs(qty) > 0.001:
                  side = "LONG" if qty > 0 else "SHORT"
                  
                  # Correct Enum Mapping
                  # book=LT, origin=OV -> LT_LONG_OV
                  tag = None
                  if book == "LT":
                       if origin == "OV":
                            tag = PositionTag.LT_LONG_OV if qty > 0 else PositionTag.LT_SHORT_OV
                       else:
                            tag = PositionTag.LT_LONG_INT if qty > 0 else PositionTag.LT_SHORT_INT
                  else:
                       if origin == "OV":
                            tag = PositionTag.MM_LONG_OV if qty > 0 else PositionTag.MM_SHORT_OV
                       else:
                            tag = PositionTag.MM_LONG_INT if qty > 0 else PositionTag.MM_SHORT_INT
                            
                  if tag:
                       tags[tag] = abs(qty)
                  
        add_tag(lt_ov_qty, "LT", "OV")
        add_tag(lt_int_qty, "LT", "INT")
        add_tag(mm_ov_qty, "MM", "OV")
        add_tag(mm_int_qty, "MM", "INT")
            
        return tags

    def _get_prev_close(self, symbol: str) -> float:
        """
        Get Previous Close price for the symbol.
        Source: StaticDataStore (janalldata.csv) or Redis fallback.
        """
        try:
            # 1. Try Static Data Store (Primary Source for Daily Prev Close)
            if self.static_store:
                # Try with normalized symbol (e.g. "MITT PRA")
                static_data = self.static_store.get_static_data(symbol)
                if static_data and static_data.get('prev_close'):
                     val = float(static_data['prev_close'])
                     if val > 0: return val
                     
                # Try with raw symbol just in case (e.g. "MITT-A")
                if "-" in symbol:
                     raw_static = self.static_store.get_static_data(symbol)
                     if raw_static and raw_static.get('prev_close'):
                         val = float(raw_static['prev_close'])
                         if val > 0: return val

            # 2. Redis Fallback (TODO: Implement when Market Data Engine populates it consistently)
            # if self.redis_client:
            #    ...
            
            return 0.0
            
        except Exception:
            return 0.0


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

