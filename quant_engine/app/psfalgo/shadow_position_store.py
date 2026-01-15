"""
PSFALGO Shadow Position Store
Simulates positions based on Execution Ledger entries (DRY-RUN only).

NO real broker interaction - pure simulation for validation.
Uses real market prices from market_data_cache.
"""

from typing import Dict, Any, Optional, List
from collections import defaultdict
from app.core.logger import logger
from app.psfalgo.execution_ledger import PSFALGOExecutionLedger


class ShadowPositionStore:
    """
    Simulates positions based on PSFALGO execution ledger entries.
    
    Tracks:
    - current_qty (net position)
    - avg_cost_long (average cost for long positions)
    - avg_cost_short (average cost for short positions)
    - exposure (total exposure)
    """
    
    def __init__(self, ledger: Optional[PSFALGOExecutionLedger] = None):
        """
        Initialize shadow position store.
        
        Args:
            ledger: PSFALGOExecutionLedger instance. If None, creates new one.
        """
        self.ledger = ledger or PSFALGOExecutionLedger()
        
        # Shadow positions cache: {symbol: position_data}
        # Will be computed from ledger entries
        self._positions_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_dirty = True
    
    def _get_market_price(self, symbol: str, position_snapshot: Optional[Dict[str, Any]] = None) -> Optional[float]:
        """
        Get market price for a symbol.
        
        Priority:
        1. last (live) from market_data_cache
        2. prev_close (hammer) from market_data_cache
        3. used_befday_cost from position_snapshot
        
        Args:
            symbol: Symbol (PREF_IBKR)
            position_snapshot: Optional position snapshot dict
            
        Returns:
            Market price or None
        """
        try:
            # Try to get from market_data_cache
            from app.api.market_data_routes import market_data_cache
            
            if market_data_cache and symbol in market_data_cache:
                market_data = market_data_cache[symbol]
                
                # Prefer last (live)
                last = market_data.get('last') or market_data.get('price')
                if last is not None and last > 0:
                    return float(last)
                
                # Fallback to prev_close (hammer)
                prev_close = market_data.get('prev_close')
                if prev_close is not None and prev_close > 0:
                    return float(prev_close)
            
            # Fallback to used_befday_cost from position_snapshot
            if position_snapshot:
                used_befday_cost = position_snapshot.get('used_befday_cost')
                if used_befday_cost is not None and used_befday_cost > 0:
                    return float(used_befday_cost)
            
            return None
            
        except Exception as e:
            logger.debug(f"Error getting market price for {symbol}: {e}")
            return None
    
    def _compute_positions_from_ledger(self) -> Dict[str, Dict[str, Any]]:
        """
        Compute shadow positions from all ledger entries.
        
        Returns:
            Dict of {symbol: position_data}
        """
        try:
            # Get all ledger entries (no limit - we need all for accurate simulation)
            entries = self.ledger.get_latest_entries(limit=10000)  # Large limit to get all
            
            # Group by symbol and process chronologically
            symbol_entries: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for entry in entries:
                symbol_entries[entry['symbol']].append(entry)
            
            # Sort each symbol's entries by timestamp
            for symbol in symbol_entries:
                symbol_entries[symbol].sort(key=lambda x: x['timestamp'])
            
            # Compute positions for each symbol
            positions = {}
            
            for symbol, entries_list in symbol_entries.items():
                current_qty = 0.0
                long_qty = 0.0
                short_qty = 0.0
                long_cost_total = 0.0
                short_cost_total = 0.0
                
                # Get current market price for this symbol
                # Use the latest entry's position_snapshot as fallback
                latest_snapshot = entries_list[-1].get('position_snapshot', {}) if entries_list else {}
                market_price_used = self._get_market_price(symbol, latest_snapshot)
                
                # Process entries chronologically
                for entry in entries_list:
                    action = entry['psfalgo_action']
                    size_lot = entry['size_lot_estimate']
                    
                    # Get price for this entry
                    # Try to get from entry's position_snapshot first
                    entry_snapshot = entry.get('position_snapshot', {})
                    price = self._get_market_price(symbol, entry_snapshot)
                    
                    # If no price available, use current market price or fallback
                    if price is None:
                        price = market_price_used or 100.0  # Final fallback
                    
                    if action == 'ADD_LONG':
                        # Add to long position
                        long_qty += size_lot
                        current_qty += size_lot
                        long_cost_total += size_lot * price
                    elif action == 'REDUCE_LONG':
                        # Reduce long position
                        reduce_qty = min(size_lot, long_qty)
                        long_qty -= reduce_qty
                        current_qty -= reduce_qty
                        # Reduce cost proportionally
                        if long_qty > 0:
                            long_cost_total = (long_cost_total / (long_qty + reduce_qty)) * long_qty
                        else:
                            long_cost_total = 0.0
                    elif action == 'ADD_SHORT':
                        # Add to short position
                        short_qty += size_lot
                        current_qty -= size_lot
                        short_cost_total += size_lot * price
                    elif action == 'REDUCE_SHORT':
                        # Reduce short position
                        reduce_qty = min(size_lot, short_qty)
                        short_qty -= reduce_qty
                        current_qty += reduce_qty
                        # Reduce cost proportionally
                        if short_qty > 0:
                            short_cost_total = (short_cost_total / (short_qty + reduce_qty)) * short_qty
                        else:
                            short_cost_total = 0.0
                
                # Calculate average costs
                avg_cost_long = long_cost_total / long_qty if long_qty > 0 else None
                avg_cost_short = short_cost_total / short_qty if short_qty > 0 else None
                
                # Get current market price (use latest if not already set)
                if market_price_used is None:
                    market_price_used = self._get_market_price(symbol, latest_snapshot) or 100.0
                
                # Calculate market values
                market_value_long = long_qty * market_price_used if long_qty > 0 else 0.0
                market_value_short = short_qty * market_price_used if short_qty > 0 else 0.0
                market_value_net = current_qty * market_price_used
                
                # Calculate exposure (absolute value of position * avg_cost)
                exposure = 0.0
                if current_qty > 0 and avg_cost_long:
                    exposure = abs(current_qty) * avg_cost_long
                elif current_qty < 0 and avg_cost_short:
                    exposure = abs(current_qty) * avg_cost_short
                
                positions[symbol] = {
                    'symbol': symbol,
                    'current_qty': round(current_qty, 2),
                    'long_qty': round(long_qty, 2),
                    'short_qty': round(short_qty, 2),
                    'avg_cost_long': round(avg_cost_long, 4) if avg_cost_long else None,
                    'avg_cost_short': round(avg_cost_short, 4) if avg_cost_short else None,
                    'market_price_used': round(market_price_used, 4) if market_price_used else None,
                    'market_value_long': round(market_value_long, 2),
                    'market_value_short': round(market_value_short, 2),
                    'market_value_net': round(market_value_net, 2),
                    'exposure': round(exposure, 2),
                    'entry_count': len(entries_list)
                }
            
            return positions
            
        except Exception as e:
            logger.error(f"Error computing shadow positions: {e}", exc_info=True)
            return {}
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get all shadow positions.
        
        Returns:
            List of position dicts
        """
        if self._cache_dirty:
            self._positions_cache = self._compute_positions_from_ledger()
            self._cache_dirty = False
        
        # Filter out zero positions
        return [
            pos for pos in self._positions_cache.values()
            if abs(pos.get('current_qty', 0)) > 0.001
        ]
    
    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get shadow position for a specific symbol.
        
        Args:
            symbol: Symbol (PREF_IBKR)
            
        Returns:
            Position dict or None
        """
        if self._cache_dirty:
            self._positions_cache = self._compute_positions_from_ledger()
            self._cache_dirty = False
        
        return self._positions_cache.get(symbol)
    
    def get_exposure_summary(self) -> Dict[str, Any]:
        """
        Get exposure summary across all shadow positions.
        
        Returns:
            Dict with total exposure, long exposure, short exposure, etc.
        """
        positions = self.get_positions()
        
        total_exposure = sum(pos.get('exposure', 0) for pos in positions)
        long_exposure = sum(
            pos.get('exposure', 0) for pos in positions 
            if pos.get('current_qty', 0) > 0
        )
        short_exposure = sum(
            pos.get('exposure', 0) for pos in positions 
            if pos.get('current_qty', 0) < 0
        )
        
        long_count = sum(1 for pos in positions if pos.get('current_qty', 0) > 0)
        short_count = sum(1 for pos in positions if pos.get('current_qty', 0) < 0)
        
        # Market values
        total_long_value = sum(
            pos.get('market_value_long', 0) for pos in positions 
            if pos.get('current_qty', 0) > 0
        )
        total_short_value = sum(
            pos.get('market_value_short', 0) for pos in positions 
            if pos.get('current_qty', 0) < 0
        )
        net_value = sum(pos.get('market_value_net', 0) for pos in positions)
        
        total_qty = sum(pos.get('current_qty', 0) for pos in positions)
        
        return {
            'total_exposure': round(total_exposure, 2),
            'long_exposure': round(long_exposure, 2),
            'short_exposure': round(short_exposure, 2),
            'net_exposure': round(long_exposure - short_exposure, 2),
            'total_long_value': round(total_long_value, 2),
            'total_short_value': round(total_short_value, 2),
            'net_value': round(net_value, 2),
            'long_count': long_count,
            'short_count': short_count,
            'symbol_count_long': long_count,  # Alias for consistency
            'symbol_count_short': short_count,  # Alias for consistency
            'total_positions': len(positions),
            'total_qty': round(total_qty, 2)
        }
    
    def invalidate_cache(self):
        """Invalidate cache to force recomputation on next access"""
        self._cache_dirty = True

