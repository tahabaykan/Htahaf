"""app/strategy/strategy_loader.py

Strategy loader - loads and hot-reloads strategies.
Supports dynamic strategy loading and reloading without engine restart.
"""

import importlib
import os
import sys
from typing import Optional, Type, Dict, List
from pathlib import Path

from app.core.logger import logger
from app.strategy.strategy_base import StrategyBase


class StrategyLoader:
    """Loads and manages strategy instances"""
    
    def __init__(self):
        self.strategies: Dict[str, StrategyBase] = {}
        self.strategy_classes: Dict[str, Type[StrategyBase]] = {}
    
    def load_strategy_class(self, strategy_name: str, module_path: Optional[str] = None) -> Optional[Type[StrategyBase]]:
        """
        Load strategy class (for optimization).
        
        Args:
            strategy_name: Strategy class name (e.g., 'ExampleStrategy')
            module_path: Module path (e.g., 'app.strategy.strategy_example')
            
        Returns:
            Strategy class or None
        """
        try:
            if module_path:
                module = importlib.import_module(module_path)
            else:
                # Default: try app.strategy.{strategy_name.lower()}
                module = importlib.import_module(f"app.strategy.{strategy_name.lower()}")
            
            strategy_class = getattr(module, strategy_name)
            
            if not issubclass(strategy_class, StrategyBase):
                logger.error(f"{strategy_name} is not a StrategyBase subclass")
                return None
            
            # Store class
            self.strategy_classes[strategy_name] = strategy_class
            
            logger.info(f"Strategy class loaded: {strategy_name}")
            return strategy_class
        
        except Exception as e:
            logger.error(f"Error loading strategy class {strategy_name}: {e}", exc_info=True)
            return None
    
    def load_strategy(self, strategy_name: str, module_path: Optional[str] = None) -> Optional[StrategyBase]:
        """
        Load strategy by name.
        
        Args:
            strategy_name: Strategy class name (e.g., 'ExampleStrategy')
            module_path: Module path (e.g., 'app.strategy.strategy_example')
            
        Returns:
            Strategy instance or None
        """
        try:
            if module_path:
                module = importlib.import_module(module_path)
            else:
                # Default: try app.strategy.{strategy_name.lower()}
                module = importlib.import_module(f"app.strategy.{strategy_name.lower()}")
            
            strategy_class = getattr(module, strategy_name)
            
            if not issubclass(strategy_class, StrategyBase):
                logger.error(f"{strategy_name} is not a StrategyBase subclass")
                return None
            
            # Create instance
            strategy = strategy_class()
            self.strategies[strategy_name] = strategy
            self.strategy_classes[strategy_name] = strategy_class
            
            logger.info(f"Strategy loaded: {strategy_name}")
            return strategy
        
        except Exception as e:
            logger.error(f"Error loading strategy {strategy_name}: {e}", exc_info=True)
            return None
    
    def reload_strategy(self, strategy_name: str) -> Optional[StrategyBase]:
        """
        Hot-reload strategy (reload module and create new instance).
        
        Args:
            strategy_name: Strategy name to reload
            
        Returns:
            New strategy instance or None
        """
        try:
            if strategy_name not in self.strategies:
                logger.warning(f"Strategy {strategy_name} not loaded, cannot reload")
                return None
            
            # Get module path
            strategy_class = self.strategy_classes[strategy_name]
            module = sys.modules[strategy_class.__module__]
            
            # Reload module
            importlib.reload(module)
            
            # Get updated class
            updated_class = getattr(module, strategy_name)
            
            # Create new instance
            new_strategy = updated_class()
            self.strategies[strategy_name] = new_strategy
            self.strategy_classes[strategy_name] = updated_class
            
            logger.info(f"Strategy reloaded: {strategy_name}")
            return new_strategy
        
        except Exception as e:
            logger.error(f"Error reloading strategy {strategy_name}: {e}", exc_info=True)
            return None
    
    def get_strategy(self, strategy_name: str) -> Optional[StrategyBase]:
        """Get strategy instance by name"""
        return self.strategies.get(strategy_name)
    
    def list_strategies(self) -> List[str]:
        """List all loaded strategies"""
        return list(self.strategies.keys())


# Global strategy loader instance
strategy_loader = StrategyLoader()

