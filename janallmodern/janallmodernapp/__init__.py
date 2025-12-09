"""
JanAllModern Application Package

Modernized version of JanAll with clean architecture:
- ui/: User interface components
- core/: Core business logic
- services/: External service integrations (Hammer, IBKR)
- utils/: Utility functions
- models/: Data models
"""

from .ui.main_window import MainWindow

__all__ = ['MainWindow']

