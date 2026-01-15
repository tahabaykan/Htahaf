"""
Strategy Context - Shared intelligence layer for all strategies

Provides access to:
- GRPAN engine (for print analysis)
- RWVAP engine (for robust VWAP)
- Port Adjuster (for group caps)
- Static data store (for FINAL_THG, AVG_ADV, etc.)
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass

from app.market_data.grpan_engine import GRPANEngine
from app.market_data.rwvap_engine import RWVAPEngine
from app.market_data.static_data_store import StaticDataStore
from app.port_adjuster.port_adjuster_store import PortAdjusterStore


@dataclass
class StrategyContext:
    """
    Shared context for all strategies.
    
    Strategies use this to access:
    - GRPAN metrics (deviation, concentration)
    - RWVAP metrics (robust VWAP)
    - Port Adjuster (group caps)
    - Static data (FINAL_THG, AVG_ADV, etc.)
    """
    grpan_engine: Optional[GRPANEngine] = None
    rwvap_engine: Optional[RWVAPEngine] = None
    static_store: Optional[StaticDataStore] = None
    port_adjuster_store: Optional[PortAdjusterStore] = None
    
    def get_grpan_for_symbol(self, symbol: str) -> Dict[str, Any]:
        """Get GRPAN metrics for symbol (latest_pan)"""
        if not self.grpan_engine:
            return {}
        return self.grpan_engine.get_grpan_for_symbol(symbol) or {}
    
    def get_grpan_all_windows(self, symbol: str) -> Dict[str, Dict[str, Any]]:
        """Get all GRPAN windows for symbol (pan_10m, pan_30m, pan_1h, pan_3h, pan_1d, pan_3d)"""
        if not self.grpan_engine:
            return {}
        return self.grpan_engine.get_all_windows_for_symbol(symbol) or {}
    
    def get_rwvap_for_symbol(self, symbol: str, window: str = '1D') -> Dict[str, Any]:
        """Get RWVAP for symbol and window"""
        if not self.rwvap_engine:
            return {}
        # RWVAP engine uses 'rwvap_1d', 'rwvap_3d', 'rwvap_5d' format
        window_name = f'rwvap_{window.lower()}' if not window.startswith('rwvap_') else window
        return self.rwvap_engine.compute_rwvap(symbol, window_name=window_name) or {}
    
    def get_rwvap_all_windows(self, symbol: str) -> Dict[str, Dict[str, Any]]:
        """Get all RWVAP windows for symbol"""
        if not self.rwvap_engine:
            return {}
        return self.rwvap_engine.get_all_rwvap_for_symbol(symbol) or {}
    
    def get_static_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get static data for symbol (FINAL_THG, AVG_ADV, etc.)"""
        if not self.static_store:
            return None
        return self.static_store.get_static_data(symbol)
    
    def get_port_adjuster_snapshot(self):
        """Get Port Adjuster snapshot (group caps)"""
        if not self.port_adjuster_store:
            return None
        return self.port_adjuster_store.get_snapshot()
    
    def get_group_max_lot(self, group_key: str, side: str = 'long') -> Optional[float]:
        """
        Get max lot for a group from Port Adjuster.
        
        Args:
            group_key: Group name (e.g., 'heldff', 'heldkuponlu')
            side: 'long' or 'short'
            
        Returns:
            Max lot for the group or None if not found
        """
        snapshot = self.get_port_adjuster_snapshot()
        if not snapshot:
            return None
        
        if side.lower() == 'long':
            allocation = snapshot.long_allocations.get(group_key)
        else:
            allocation = snapshot.short_allocations.get(group_key)
        
        return allocation.max_lot if allocation else None

