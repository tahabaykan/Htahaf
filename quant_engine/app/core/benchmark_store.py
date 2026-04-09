"""
BenchmarkStore - ETF Benchmark Data (STATELESS)

Manages ETF benchmark data as input for score calculations.
ETFs are NOT securities - they don't get SecurityContext objects.

Key Principles:
- ETFs store only: percent_change, cent_change, timestamp
- No L1/Truth/Position tracking for ETFs
- Used as input to FastScoreCalculator
- Missing benchmark = status flag, not crash
"""

from typing import Dict, Optional, List, Any
from dataclasses import dataclass
from datetime import datetime

from app.core.logger import logger
from app.core.safe_access import safe_num, is_fresh


@dataclass
class BenchmarkSnapshot:
    """Single ETF benchmark data point."""
    symbol: str
    percent_change: float
    cent_change: float
    last_price: Optional[float] = None
    prev_close: Optional[float] = None
    ts: Optional[datetime] = None
    
    def is_fresh(self, max_age_seconds: float = 120.0) -> bool:
        """Check if benchmark data is fresh."""
        return is_fresh(self.ts, max_age_seconds)


class BenchmarkStore:
    """
    ETF Benchmark Store - STATELESS per-ETF design.
    
    ETFs tracked:
    - TLT, IEF, IEI (Treasury)
    - PFF, PGF (Preferred)
    - KRE (Regional Banks)
    - IWM (Small Cap)
    - SPY (S&P 500)
    """
    
    # Standard ETF symbols we track
    ETF_SYMBOLS = {"TLT", "IEF", "IEI", "PFF", "PGF", "KRE", "IWM", "SPY"}
    
    # Key benchmarks that must be available
    REQUIRED_BENCHMARKS = {"TLT", "PFF", "SPY"}
    
    def __init__(self):
        self._snapshots: Dict[str, BenchmarkSnapshot] = {}
        self._prev_closes: Dict[str, float] = {}
        self._created_at = datetime.now()
    
    # =========================================================================
    # Update Methods
    # =========================================================================
    
    def update(
        self,
        symbol: str,
        percent_change: Optional[float] = None,
        cent_change: Optional[float] = None,
        last_price: Optional[float] = None,
        prev_close: Optional[float] = None,
        ts: Optional[datetime] = None
    ) -> None:
        """
        Update ETF benchmark data.
        
        Args:
            symbol: ETF symbol (e.g., "TLT")
            percent_change: Percent change from prev close
            cent_change: Absolute change in cents/dollars
            last_price: Current price
            prev_close: Previous close price
            ts: Timestamp
        """
        if not symbol:
            return
        
        normalized = symbol.strip().upper()
        
        # Store prev_close if provided
        if prev_close is not None:
            self._prev_closes[normalized] = safe_num(prev_close)
        
        # Calculate changes if we have prices but not changes
        stored_prev_close = self._prev_closes.get(normalized)
        
        if percent_change is None and last_price is not None and stored_prev_close:
            percent_change = ((last_price - stored_prev_close) / stored_prev_close) * 100
        
        if cent_change is None and last_price is not None and stored_prev_close:
            cent_change = last_price - stored_prev_close
        
        self._snapshots[normalized] = BenchmarkSnapshot(
            symbol=normalized,
            percent_change=safe_num(percent_change, 0.0),
            cent_change=safe_num(cent_change, 0.0),
            last_price=safe_num(last_price),
            prev_close=stored_prev_close,
            ts=ts or datetime.now()
        )
    
    def update_from_l1(
        self,
        symbol: str,
        last_price: float,
        ts: Optional[datetime] = None
    ) -> None:
        """
        Update benchmark from L1 last price.
        Will calculate percent_change if prev_close is known.
        """
        self.update(
            symbol=symbol,
            last_price=last_price,
            ts=ts
        )
    
    def set_prev_close(self, symbol: str, prev_close: float) -> None:
        """Set prev_close for an ETF (from daily CSV)."""
        if symbol and prev_close:
            self._prev_closes[symbol.strip().upper()] = safe_num(prev_close)
    
    def set_prev_closes_bulk(self, prev_closes: Dict[str, float]) -> None:
        """Set multiple prev_closes at once."""
        for symbol, price in prev_closes.items():
            self.set_prev_close(symbol, price)
    
    # =========================================================================
    # Access Methods
    # =========================================================================
    
    def get(self, symbol: str) -> Optional[BenchmarkSnapshot]:
        """Get benchmark snapshot for an ETF."""
        if not symbol:
            return None
        return self._snapshots.get(symbol.strip().upper())
    
    def get_percent_change(self, symbol: str, default: float = 0.0) -> float:
        """Get percent change for an ETF."""
        snapshot = self.get(symbol)
        if snapshot and snapshot.percent_change is not None:
            return snapshot.percent_change
        return default
    
    def get_cent_change(self, symbol: str, default: float = 0.0) -> float:
        """Get cent change for an ETF."""
        snapshot = self.get(symbol)
        if snapshot and snapshot.cent_change is not None:
            return snapshot.cent_change
        return default
    
    def get_all(self) -> Dict[str, BenchmarkSnapshot]:
        """Get all benchmark snapshots."""
        return self._snapshots.copy()
    
    # =========================================================================
    # Status Methods
    # =========================================================================
    
    def is_available(self) -> bool:
        """
        Check if key benchmarks are available.
        Returns True if all REQUIRED_BENCHMARKS have fresh data.
        """
        for symbol in self.REQUIRED_BENCHMARKS:
            snapshot = self._snapshots.get(symbol)
            if not snapshot or not snapshot.is_fresh():
                return False
        return True
    
    def get_missing_benchmarks(self) -> List[str]:
        """Get list of missing or stale required benchmarks."""
        missing = []
        for symbol in self.REQUIRED_BENCHMARKS:
            snapshot = self._snapshots.get(symbol)
            if not snapshot:
                missing.append(f"{symbol}:MISSING")
            elif not snapshot.is_fresh():
                missing.append(f"{symbol}:STALE")
        return missing
    
    def get_available_count(self) -> int:
        """Get count of available benchmarks."""
        return len(self._snapshots)
    
    def get_fresh_count(self) -> int:
        """Get count of fresh benchmarks."""
        return sum(1 for s in self._snapshots.values() if s.is_fresh())
    
    # =========================================================================
    # Serialization
    # =========================================================================
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API."""
        return {
            "benchmarks": {
                symbol: {
                    "percent_change": snap.percent_change,
                    "cent_change": snap.cent_change,
                    "last_price": snap.last_price,
                    "prev_close": snap.prev_close,
                    "ts": snap.ts.isoformat() if snap.ts else None,
                    "is_fresh": snap.is_fresh()
                }
                for symbol, snap in self._snapshots.items()
            },
            "is_available": self.is_available(),
            "missing": self.get_missing_benchmarks(),
            "available_count": self.get_available_count(),
            "fresh_count": self.get_fresh_count()
        }
    
    def get_summary(self) -> str:
        """Get one-line summary for logging."""
        fresh = self.get_fresh_count()
        total = self.get_available_count()
        available = "OK" if self.is_available() else "MISSING"
        return f"benchmarks={total} fresh={fresh} status={available}"


# =============================================================================
# Global Singleton
# =============================================================================

_benchmark_store: Optional[BenchmarkStore] = None


def get_benchmark_store() -> BenchmarkStore:
    """Get global BenchmarkStore instance."""
    global _benchmark_store
    if _benchmark_store is None:
        _benchmark_store = BenchmarkStore()
    return _benchmark_store


def initialize_benchmark_store() -> BenchmarkStore:
    """Initialize global BenchmarkStore instance."""
    global _benchmark_store
    _benchmark_store = BenchmarkStore()
    logger.info("[BENCHMARK_STORE] Initialized")
    return _benchmark_store
