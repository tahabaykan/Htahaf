"""
User Action Store
Stores and retrieves user decisions on orders (APPROVE, REJECT, HOLD).

This is a human decision layer AFTER Gate, BEFORE execution.
"""

import json
import time
from typing import Dict, Any, Optional
from pathlib import Path

from app.core.logger import logger


class UserActionStore:
    """
    Stores user actions on orders.
    
    User actions:
    - APPROVE: User approved the order (can proceed to execution)
    - REJECT: User rejected the order (do not execute)
    - HOLD: User wants to hold/watch (defer decision)
    
    This is a human-in-the-loop decision layer - NO execution.
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize with storage path.
        
        Args:
            storage_path: Path to JSON file for persistence (optional, uses in-memory if None)
        """
        if storage_path is None:
            # Default to data/user_actions.json relative to project root
            project_root = Path(__file__).parent.parent.parent
            data_dir = project_root / "data"
            data_dir.mkdir(exist_ok=True)
            storage_path = data_dir / "user_actions.json"
        
        self.storage_path = Path(storage_path)
        self._actions: Dict[str, Dict[str, Any]] = {}  # {symbol: {user_action, user_note, timestamp, gate_status}}
        self._load_actions()
    
    def _load_actions(self):
        """Load actions from storage file"""
        try:
            if self.storage_path.exists():
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._actions = data.get('actions', {})
                logger.info(f"Loaded {len(self._actions)} user actions from {self.storage_path}")
            else:
                logger.info(f"User actions file not found, starting with empty store")
        except Exception as e:
            logger.error(f"Error loading user actions: {e}", exc_info=True)
            self._actions = {}
    
    def _save_actions(self):
        """Save actions to storage file"""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump({
                    'actions': self._actions,
                    'last_updated': time.time()
                }, f, indent=2)
            logger.debug(f"Saved {len(self._actions)} user actions to {self.storage_path}")
        except Exception as e:
            logger.error(f"Error saving user actions: {e}", exc_info=True)
    
    def set_user_action(
        self,
        symbol: str,
        user_action: str,
        user_note: Optional[str] = None,
        gate_status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Set user action for a symbol.
        
        Args:
            symbol: Symbol identifier (PREF_IBKR)
            user_action: 'APPROVE', 'REJECT', or 'HOLD'
            user_note: Optional note from user
            gate_status: Gate status at time of action (for context)
            
        Returns:
            Action record dict
        """
        if user_action not in ['APPROVE', 'REJECT', 'HOLD']:
            raise ValueError(f"Invalid user_action: {user_action}. Must be APPROVE, REJECT, or HOLD")
        
        action_record = {
            'user_action': user_action,
            'user_note': user_note,
            'timestamp': time.time(),
            'gate_status': gate_status
        }
        
        self._actions[symbol] = action_record
        self._save_actions()
        
        logger.info(f"User action set for {symbol}: {user_action}")
        
        return action_record
    
    def get_user_action(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get user action for a symbol.
        
        Args:
            symbol: Symbol identifier
            
        Returns:
            Action record dict or None if not found
        """
        return self._actions.get(symbol)
    
    def clear_user_action(self, symbol: str):
        """Clear user action for a symbol"""
        if symbol in self._actions:
            del self._actions[symbol]
            self._save_actions()
            logger.info(f"User action cleared for {symbol}")
    
    def get_all_actions(self) -> Dict[str, Dict[str, Any]]:
        """Get all user actions"""
        return self._actions.copy()
    
    def get_action_summary(self) -> Dict[str, int]:
        """Get summary of actions by type"""
        summary = {'APPROVE': 0, 'REJECT': 0, 'HOLD': 0, 'TOTAL': len(self._actions)}
        for action_record in self._actions.values():
            action = action_record.get('user_action')
            if action in summary:
                summary[action] += 1
        return summary








