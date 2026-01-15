"""
JFIN Store - In-memory state management for JFIN

Manages JFIN state across all 4 tabs (BB, FB, SAS, SFS)
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field, asdict

from app.core.logger import logger


@dataclass
class JFINState:
    """JFIN State - All 4 tabs"""
    bb_stocks: List[Dict[str, Any]] = field(default_factory=list)
    fb_stocks: List[Dict[str, Any]] = field(default_factory=list)
    sas_stocks: List[Dict[str, Any]] = field(default_factory=list)
    sfs_stocks: List[Dict[str, Any]] = field(default_factory=list)
    
    percentage: int = 50  # %25, %50, %75, %100
    ntumcsv_settings: Optional[Dict[str, Any]] = None
    
    last_updated: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        if self.last_updated:
            result['last_updated'] = self.last_updated.isoformat()
        return result


class JFINStore:
    """
    JFIN Store - Singleton pattern
    
    Manages in-memory JFIN state for all 4 tabs
    """
    
    _instance: Optional['JFINStore'] = None
    _state: Optional[JFINState] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._state = JFINState()
            logger.info("[JFIN_STORE] Initialized")
        return cls._instance
    
    def update_state(
        self,
        bb_stocks: Optional[List[Dict[str, Any]]] = None,
        fb_stocks: Optional[List[Dict[str, Any]]] = None,
        sas_stocks: Optional[List[Dict[str, Any]]] = None,
        sfs_stocks: Optional[List[Dict[str, Any]]] = None,
        percentage: Optional[int] = None,
        ntumcsv_settings: Optional[Dict[str, Any]] = None
    ):
        """Update JFIN state"""
        if bb_stocks is not None:
            self._state.bb_stocks = bb_stocks
        if fb_stocks is not None:
            self._state.fb_stocks = fb_stocks
        if sas_stocks is not None:
            self._state.sas_stocks = sas_stocks
        if sfs_stocks is not None:
            self._state.sfs_stocks = sfs_stocks
        if percentage is not None:
            self._state.percentage = percentage
        if ntumcsv_settings is not None:
            self._state.ntumcsv_settings = ntumcsv_settings
        
        self._state.last_updated = datetime.now()
        logger.info(f"[JFIN_STORE] State updated: BB={len(self._state.bb_stocks)}, FB={len(self._state.fb_stocks)}, SAS={len(self._state.sas_stocks)}, SFS={len(self._state.sfs_stocks)}, Percentage={self._state.percentage}")
    
    def get_state(self) -> JFINState:
        """Get current JFIN state"""
        return self._state
    
    def get_tab_stocks(self, tab_name: str) -> List[Dict[str, Any]]:
        """Get stocks for specific tab"""
        tab_name = tab_name.upper()
        if tab_name == 'BB':
            return self._state.bb_stocks
        elif tab_name == 'FB':
            return self._state.fb_stocks
        elif tab_name == 'SAS':
            return self._state.sas_stocks
        elif tab_name == 'SFS':
            return self._state.sfs_stocks
        else:
            logger.warning(f"[JFIN_STORE] Unknown tab name: {tab_name}")
            return []
    
    def get_percentage(self) -> int:
        """Get current percentage"""
        return self._state.percentage
    
    def set_percentage(self, percentage: int):
        """Set percentage"""
        if percentage not in [25, 50, 75, 100]:
            raise ValueError(f"Invalid percentage: {percentage}. Must be 25, 50, 75, or 100")
        self._state.percentage = percentage
        self._state.last_updated = datetime.now()
        logger.info(f"[JFIN_STORE] Percentage set to {percentage}%")
    
    def clear_state(self):
        """Clear JFIN state"""
        self._state = JFINState()
        logger.info("[JFIN_STORE] State cleared")


# Global instance getter
def get_jfin_store() -> JFINStore:
    """Get global JFIN store instance"""
    return JFINStore()





