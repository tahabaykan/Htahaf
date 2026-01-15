"""
Execution Service

The ONLY component that talks to the broker (IBKR).
Owns order lifecycle: place, cancel, replace, track fills.
"""

from .service import ExecutionService

__all__ = ["ExecutionService"]



