"""
SecurityContext - Single Source of Truth for Each Security

Each preferred stock (identified by PREF_IBKR) has ONE SecurityContext object
that consolidates ALL data about that security:
- L1 Data (bid/ask/last)
- Truth Tick Data (dominant price, prints)
- Static Data (thresholds, ADV)
- Derived Metrics (spread, daily change)
- Position State (qty, cost, PnL)
- Data Status (missing/stale flags with reason codes)

Key Principles:
- Getters NEVER throw exceptions
- Missing data = status flag + reason code, not crash
- Updates are O(1), mark dirty flags
- Score calculation is EXTERNAL (FastScoreCalculator)
- Thread-safe with per-context lock
"""

from typing import Any, Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import threading

from app.core.safe_access import DataStatus, safe_num, is_fresh


# =============================================================================
# Missing Reason Codes
# =============================================================================

class MissingReasonCode(Enum):
    """Detailed reason codes for missing/invalid data."""
    OK = "OK"
    
    # L1 Issues
    NO_L1_BIDASK = "NO_L1_BIDASK"
    NO_L1_LAST = "NO_L1_LAST"
    STALE_L1 = "STALE_L1"
    INVALID_L1 = "INVALID_L1"
    
    # Static Issues
    NO_STATIC = "NO_STATIC"
    NO_PREV_CLOSE = "NO_PREV_CLOSE"
    NO_THRESHOLDS = "NO_THRESHOLDS"
    
    # Truth Issues
    NO_TRUTH = "NO_TRUTH"
    STALE_TRUTH = "STALE_TRUTH"
    
    # Score Issues
    NO_SCORES = "NO_SCORES"
    STALE_SCORES = "STALE_SCORES"
    
    # Symbol Issues
    UNKNOWN_SYMBOL = "UNKNOWN_SYMBOL"
    
    # Benchmark Issues
    NO_BENCHMARK = "NO_BENCHMARK"
    
    # Policy Issues
    DEFENSIVE_MODE = "DEFENSIVE_MODE"


# =============================================================================
# State Components
# =============================================================================

@dataclass
class L1State:
    """Level 1 market data (bid/ask/last)."""
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    volume: Optional[int] = None
    ts: Optional[datetime] = None
    source: str = "UNKNOWN"
    
    def is_valid(self) -> bool:
        """Check if L1 data is valid (has bid and ask > 0)."""
        return (
            self.bid is not None and 
            self.ask is not None and 
            self.bid > 0 and 
            self.ask > 0
        )
    
    def is_fresh(self, max_age_seconds: float = 60.0) -> bool:
        """Check if L1 data is fresh."""
        return is_fresh(self.ts, max_age_seconds)
    
    def get_age_seconds(self) -> Optional[float]:
        """Get age of L1 data in seconds."""
        if self.ts is None:
            return None
        return (datetime.now() - self.ts).total_seconds()


@dataclass
class TruthState:
    """Truth tick data from GRPAN."""
    dominant_price: Optional[float] = None
    turn_count: int = 0
    concentration_percent: Optional[float] = None
    grpan_ort_dev: Optional[float] = None
    last_prints: List[float] = field(default_factory=list)
    ts: Optional[datetime] = None
    
    def is_valid(self) -> bool:
        """Check if truth data is valid."""
        return self.dominant_price is not None and self.dominant_price > 0
    
    def is_fresh(self, max_age_seconds: float = 120.0) -> bool:
        """Check if truth data is fresh (longer tolerance than L1)."""
        return is_fresh(self.ts, max_age_seconds)


@dataclass
class StaticInfo:
    """Static data from CSV (janalldata.csv)."""
    final_thg: Optional[float] = None
    short_final: Optional[float] = None
    avg_adv: Optional[float] = None
    group: Optional[str] = None
    cmon: Optional[str] = None
    cgrup: Optional[str] = None
    maxalw: int = 2000
    prev_close: Optional[float] = None
    sma63_chg: Optional[float] = None
    sma246_chg: Optional[float] = None
    
    def is_loaded(self) -> bool:
        """Check if static data has been loaded."""
        return self.final_thg is not None or self.avg_adv is not None
    
    def has_prev_close(self) -> bool:
        """Check if prev_close is available."""
        return self.prev_close is not None and self.prev_close > 0


@dataclass 
class DerivedMetrics:
    """Derived/calculated metrics (computed from L1 + Static)."""
    spread: Optional[float] = None
    spread_percent: Optional[float] = None
    mid: Optional[float] = None
    daily_change: Optional[float] = None
    daily_change_percent: Optional[float] = None
    last_computed: Optional[datetime] = None
    
    def is_computed(self) -> bool:
        """Check if metrics have been computed."""
        return self.spread is not None


@dataclass
class ScoreState:
    """
    Score storage - EXTERNAL calculation only.
    Scores are computed by FastScoreCalculator, NOT by SecurityContext.
    """
    bid_buy_ucuzluk: Optional[float] = None
    ask_sell_pahalilik: Optional[float] = None
    front_buy_ucuzluk: Optional[float] = None
    front_sell_pahalilik: Optional[float] = None
    fbtot: Optional[float] = None
    sfstot: Optional[float] = None
    gort: Optional[float] = None
    final_fb_skor: Optional[float] = None
    final_sfs_skor: Optional[float] = None
    final_bb_skor: Optional[float] = None
    final_sas_skor: Optional[float] = None
    bench_chg: Optional[float] = None  # NEW: Group-based Benchmark Change
    last_computed: Optional[datetime] = None
    computed_by: str = "UNKNOWN"
    
    def has_scores(self) -> bool:
        """Check if any scores are available."""
        return self.bid_buy_ucuzluk is not None or self.ask_sell_pahalilik is not None
    
    def is_fresh(self, max_age_seconds: float = 60.0) -> bool:
        """Check if scores are fresh."""
        return is_fresh(self.last_computed, max_age_seconds)


@dataclass
class PositionState:
    """Current position state from broker."""
    qty: float = 0.0
    avg_cost: Optional[float] = None
    market_value: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    realized_pnl: Optional[float] = None
    ts: Optional[datetime] = None
    
    def has_position(self) -> bool:
        """Check if there's an open position."""
        return self.qty != 0
    
    def is_long(self) -> bool:
        """Check if position is long."""
        return self.qty > 0
    
    def is_short(self) -> bool:
        """Check if position is short."""
        return self.qty < 0


@dataclass
class StatusInfo:
    """
    Detailed status tracking for debugging.
    Answers: "Why is this security not eligible?"
    """
    missing_fields: Set[str] = field(default_factory=set)
    stale_fields: Set[str] = field(default_factory=set)
    missing_reason: MissingReasonCode = MissingReasonCode.OK
    last_update_by_source: Dict[str, datetime] = field(default_factory=dict)
    
    def update_source_ts(self, source: str) -> None:
        """Record update timestamp for a source."""
        self.last_update_by_source[source] = datetime.now()


# =============================================================================
# SecurityContext - Main Container
# =============================================================================

class SecurityContext:
    """
    Single Source of Truth for a preferred stock.
    
    All data about a security is consolidated here.
    All access is safe - getters never throw exceptions.
    Thread-safe with per-context lock.
    
    NOTE: Scores are stored here but COMPUTED EXTERNALLY by FastScoreCalculator.
    """
    
    # Stale thresholds
    L1_STALE_SECONDS = 60.0
    L1_ENGINE_STALE_SECONDS = 15.0
    TRUTH_STALE_SECONDS = 120.0
    SCORE_STALE_SECONDS = 60.0
    
    def __init__(self, pref_ibkr: str):
        # Identity
        self.pref_ibkr = pref_ibkr
        
        # State components
        self.l1 = L1State()
        self.truth = TruthState()
        self.static = StaticInfo()
        self.derived = DerivedMetrics()
        self.scores = ScoreState()
        self.position = PositionState()
        self.status = StatusInfo()
        
        # Metadata
        self.created_at = datetime.now()
        self.last_updated: Optional[datetime] = None
        
        # Dirty flags for incremental updates
        self._derived_dirty = True
        
        # Thread safety - per-context lock
        self._lock = threading.RLock()
    
    # =========================================================================
    # Safe Getters
    # =========================================================================
    
    def get_value(self, field_path: str, default: Any = None) -> Tuple[Any, DataStatus]:
        """
        Safe getter for any field. NEVER throws exception.
        
        Args:
            field_path: Dot-separated path (e.g., "l1.bid", "scores.fbtot")
            default: Default value if not found
            
        Returns:
            Tuple of (value, status)
        """
        try:
            parts = field_path.split('.')
            current = self
            
            for part in parts:
                if current is None:
                    return (default, DataStatus.MISSING)
                
                if hasattr(current, part):
                    current = getattr(current, part, None)
                elif hasattr(current, 'get'):
                    current = current.get(part, None)
                else:
                    return (default, DataStatus.MISSING)
            
            if current is None:
                return (default, DataStatus.MISSING)
            
            return (current, DataStatus.OK)
            
        except Exception:
            return (default, DataStatus.INVALID)
    
    def get_bid(self) -> Optional[float]:
        """Get bid price safely."""
        return self.l1.bid
    
    def get_ask(self) -> Optional[float]:
        """Get ask price safely."""
        return self.l1.ask
    
    def get_last(self) -> Optional[float]:
        """Get last price safely."""
        return self.l1.last
    
    def get_spread(self) -> Optional[float]:
        """Get spread safely (compute if dirty)."""
        if self._derived_dirty:
            self._compute_derived_if_needed()
        return self.derived.spread
    
    def get_mid(self) -> Optional[float]:
        """Get mid price safely."""
        if self._derived_dirty:
            self._compute_derived_if_needed()
        return self.derived.mid
    
    # =========================================================================
    # Update Methods (Thread-Safe)
    # =========================================================================
    
    def update_l1(
        self,
        bid: Optional[float] = None,
        ask: Optional[float] = None,
        last: Optional[float] = None,
        volume: Optional[int] = None,
        ts: Optional[datetime] = None,
        source: str = "UNKNOWN"
    ) -> None:
        """Update L1 data. Thread-safe."""
        with self._lock:
            if bid is not None:
                self.l1.bid = safe_num(bid)
            if ask is not None:
                self.l1.ask = safe_num(ask)
            if last is not None:
                self.l1.last = safe_num(last)
            if volume is not None:
                self.l1.volume = volume
            
            self.l1.ts = ts or datetime.now()
            self.l1.source = source
            
            # Mark derived as dirty
            self._derived_dirty = True
            self.last_updated = datetime.now()
            self.status.update_source_ts(f"L1_{source}")
    
    def update_truth(
        self,
        dominant_price: Optional[float] = None,
        turn_count: Optional[int] = None,
        concentration_percent: Optional[float] = None,
        grpan_ort_dev: Optional[float] = None,
        last_prints: Optional[List[float]] = None,
        ts: Optional[datetime] = None
    ) -> None:
        """Update truth tick data. Thread-safe."""
        with self._lock:
            if dominant_price is not None:
                self.truth.dominant_price = safe_num(dominant_price)
            if turn_count is not None:
                self.truth.turn_count = turn_count
            if concentration_percent is not None:
                self.truth.concentration_percent = safe_num(concentration_percent)
            if grpan_ort_dev is not None:
                self.truth.grpan_ort_dev = safe_num(grpan_ort_dev)
            if last_prints is not None:
                self.truth.last_prints = last_prints
            
            self.truth.ts = ts or datetime.now()
            self.last_updated = datetime.now()
            self.status.update_source_ts("TRUTH")
    
    def update_static(
        self,
        final_thg: Optional[float] = None,
        short_final: Optional[float] = None,
        avg_adv: Optional[float] = None,
        group: Optional[str] = None,
        cmon: Optional[str] = None,
        cgrup: Optional[str] = None,
        maxalw: Optional[int] = None,
        prev_close: Optional[float] = None,
        sma63_chg: Optional[float] = None,
        sma246_chg: Optional[float] = None
    ) -> None:
        """Update static data. Thread-safe."""
        with self._lock:
            if final_thg is not None:
                self.static.final_thg = safe_num(final_thg)
            if short_final is not None:
                self.static.short_final = safe_num(short_final)
            if avg_adv is not None:
                self.static.avg_adv = safe_num(avg_adv)
            if group is not None:
                self.static.group = group
            if cmon is not None:
                self.static.cmon = cmon
            if cgrup is not None:
                self.static.cgrup = cgrup
            if maxalw is not None:
                self.static.maxalw = maxalw
            if prev_close is not None:
                self.static.prev_close = safe_num(prev_close)
            if sma63_chg is not None:
                self.static.sma63_chg = safe_num(sma63_chg)
            if sma246_chg is not None:
                self.static.sma246_chg = safe_num(sma246_chg)
            
            self._derived_dirty = True
            self.last_updated = datetime.now()
            self.status.update_source_ts("STATIC")
    
    def update_position(
        self,
        qty: Optional[float] = None,
        avg_cost: Optional[float] = None,
        market_value: Optional[float] = None,
        unrealized_pnl: Optional[float] = None,
        realized_pnl: Optional[float] = None,
        ts: Optional[datetime] = None
    ) -> None:
        """Update position state. Thread-safe."""
        with self._lock:
            if qty is not None:
                self.position.qty = safe_num(qty, 0.0)
            if avg_cost is not None:
                self.position.avg_cost = safe_num(avg_cost)
            if market_value is not None:
                self.position.market_value = safe_num(market_value)
            if unrealized_pnl is not None:
                self.position.unrealized_pnl = safe_num(unrealized_pnl)
            if realized_pnl is not None:
                self.position.realized_pnl = safe_num(realized_pnl)
            
            self.position.ts = ts or datetime.now()
            self.last_updated = datetime.now()
            self.status.update_source_ts("POSITION")
    
    def update_scores(
        self,
        bid_buy_ucuzluk: Optional[float] = None,
        ask_sell_pahalilik: Optional[float] = None,
        front_buy_ucuzluk: Optional[float] = None,
        front_sell_pahalilik: Optional[float] = None,
        fbtot: Optional[float] = None,
        sfstot: Optional[float] = None,
        gort: Optional[float] = None,
        final_fb_skor: Optional[float] = None,
        final_sfs_skor: Optional[float] = None,
        final_bb_skor: Optional[float] = None,
        final_sas_skor: Optional[float] = None,
        bench_chg: Optional[float] = None, # NEW
        computed_by: str = "UNKNOWN"
    ) -> None:
        """
        Update pre-computed scores. Thread-safe.
        
        NOTE: This is called by FastScoreCalculator, NOT computed internally.
        """
        with self._lock:
            if bid_buy_ucuzluk is not None:
                self.scores.bid_buy_ucuzluk = safe_num(bid_buy_ucuzluk)
            if ask_sell_pahalilik is not None:
                self.scores.ask_sell_pahalilik = safe_num(ask_sell_pahalilik)
            if front_buy_ucuzluk is not None:
                self.scores.front_buy_ucuzluk = safe_num(front_buy_ucuzluk)
            if front_sell_pahalilik is not None:
                self.scores.front_sell_pahalilik = safe_num(front_sell_pahalilik)
            if fbtot is not None:
                self.scores.fbtot = safe_num(fbtot)
            if sfstot is not None:
                self.scores.sfstot = safe_num(sfstot)
            if gort is not None:
                self.scores.gort = safe_num(gort)
            if final_fb_skor is not None:
                self.scores.final_fb_skor = safe_num(final_fb_skor)
            if final_sfs_skor is not None:
                self.scores.final_sfs_skor = safe_num(final_sfs_skor)
            if final_bb_skor is not None:
                self.scores.final_bb_skor = safe_num(final_bb_skor)
            if final_sas_skor is not None:
                self.scores.final_sas_skor = safe_num(final_sas_skor)
            if bench_chg is not None:
                self.scores.bench_chg = safe_num(bench_chg)
            
            self.scores.last_computed = datetime.now()
            self.scores.computed_by = computed_by
            self.last_updated = datetime.now()
            self.status.update_source_ts(f"SCORES_{computed_by}")
    
    # =========================================================================
    # Computed Properties
    # =========================================================================
    
    def _compute_derived_if_needed(self) -> None:
        """Compute derived metrics from L1 if dirty."""
        if not self._derived_dirty:
            return
        
        with self._lock:
            if not self.l1.is_valid():
                return
            
            bid = self.l1.bid
            ask = self.l1.ask
            
            # Spread
            self.derived.spread = ask - bid
            
            # Mid
            self.derived.mid = (bid + ask) / 2
            
            # Spread percent
            if self.derived.mid > 0:
                self.derived.spread_percent = (self.derived.spread / self.derived.mid) * 100
            
            # Daily change (if prev_close available)
            if self.static.has_prev_close():
                current = self.l1.last or self.derived.mid
                if current:
                    self.derived.daily_change = current - self.static.prev_close
                    self.derived.daily_change_percent = (self.derived.daily_change / self.static.prev_close) * 100
            
            self.derived.last_computed = datetime.now()
            self._derived_dirty = False
    
    # =========================================================================
    # Status Methods
    # =========================================================================
    
    def get_status(self) -> DataStatus:
        """Get overall data status."""
        if not self.l1.is_valid():
            return DataStatus.MISSING
        if not self.l1.is_fresh(self.L1_STALE_SECONDS):
            return DataStatus.STALE
        return DataStatus.OK
    
    def get_missing_reason(self, for_engine: bool = False) -> MissingReasonCode:
        """
        Get the primary reason why this security might not be eligible.
        
        Args:
            for_engine: If True, use stricter thresholds for engine decisions
            
        Returns:
            MissingReasonCode
        """
        stale_threshold = self.L1_ENGINE_STALE_SECONDS if for_engine else self.L1_STALE_SECONDS
        
        # L1 checks
        if not self.l1.is_valid():
            if self.l1.bid is None or self.l1.ask is None:
                return MissingReasonCode.NO_L1_BIDASK
            return MissingReasonCode.INVALID_L1
        
        if not self.l1.is_fresh(stale_threshold):
            return MissingReasonCode.STALE_L1
        
        # Static checks
        if not self.static.is_loaded():
            return MissingReasonCode.NO_STATIC
        
        if not self.static.has_prev_close():
            return MissingReasonCode.NO_PREV_CLOSE
        
        # Score checks (only for engine)
        if for_engine and not self.scores.has_scores():
            return MissingReasonCode.NO_SCORES
        
        return MissingReasonCode.OK
    
    def get_missing_fields(self) -> List[str]:
        """Get list of missing critical fields."""
        missing = []
        
        if not self.l1.is_valid():
            missing.append("L1")
        if not self.static.is_loaded():
            missing.append("STATIC")
        if not self.scores.has_scores():
            missing.append("SCORES")
        if not self.static.has_prev_close():
            missing.append("PREV_CLOSE")
        
        return missing
    
    def get_stale_fields(self) -> List[str]:
        """Get list of stale data fields."""
        stale = []
        
        if self.l1.ts and not self.l1.is_fresh(self.L1_STALE_SECONDS):
            stale.append("L1")
        if self.truth.ts and not self.truth.is_fresh(self.TRUTH_STALE_SECONDS):
            stale.append("TRUTH")
        if self.scores.last_computed and not self.scores.is_fresh(self.SCORE_STALE_SECONDS):
            stale.append("SCORES")
        
        return stale
    
    def is_tradeable(self, for_engine: bool = False) -> bool:
        """
        Check if security has enough data to trade.
        
        Args:
            for_engine: If True, use stricter thresholds
        """
        stale_threshold = self.L1_ENGINE_STALE_SECONDS if for_engine else self.L1_STALE_SECONDS
        
        return (
            self.l1.is_valid() and
            self.l1.is_fresh(stale_threshold) and
            self.static.is_loaded()
        )
    
    # =========================================================================
    # Serialization
    # =========================================================================
    
    def to_dict(self, include_heavy: bool = False) -> Dict[str, Any]:
        """
        Convert to dictionary for API/serialization.
        
        Args:
            include_heavy: Include heavy data like truth prints
        """
        with self._lock:
            result = {
                "pref_ibkr": self.pref_ibkr,
                "l1": {
                    "bid": self.l1.bid,
                    "ask": self.l1.ask,
                    "last": self.l1.last,
                    "ts": self.l1.ts.isoformat() if self.l1.ts else None,
                    "source": self.l1.source,
                    "is_valid": self.l1.is_valid(),
                    "is_fresh": self.l1.is_fresh(),
                    "age_seconds": self.l1.get_age_seconds()
                },
                "derived": {
                    "spread": self.derived.spread,
                    "spread_percent": self.derived.spread_percent,
                    "mid": self.derived.mid,
                    "daily_change": self.derived.daily_change,
                    "daily_change_percent": self.derived.daily_change_percent
                },
                "scores": {
                    "bid_buy_ucuzluk": self.scores.bid_buy_ucuzluk,
                    "ask_sell_pahalilik": self.scores.ask_sell_pahalilik,
                    "fbtot": self.scores.fbtot,
                    "sfstot": self.scores.sfstot,
                    "gort": self.scores.gort,
                    "bench_chg": self.scores.bench_chg, # NEW
                    "has_scores": self.scores.has_scores()
                },
                "position": {
                    "qty": self.position.qty,
                    "avg_cost": self.position.avg_cost,
                    "market_value": self.position.market_value,
                    "unrealized_pnl": self.position.unrealized_pnl,
                    "has_position": self.position.has_position()
                },
                "status": self.get_status().value,
                "missing_reason": self.get_missing_reason().value,
                "missing_fields": self.get_missing_fields(),
                "stale_fields": self.get_stale_fields(),
                "is_tradeable": self.is_tradeable(),
                "last_updated": self.last_updated.isoformat() if self.last_updated else None
            }
            
            if include_heavy:
                result["truth"] = {
                    "dominant_price": self.truth.dominant_price,
                    "turn_count": self.truth.turn_count,
                    "concentration_percent": self.truth.concentration_percent,
                    "last_prints": self.truth.last_prints[-10:] if self.truth.last_prints else [],
                    "ts": self.truth.ts.isoformat() if self.truth.ts else None
                }
                result["static"] = {
                    "final_thg": self.static.final_thg,
                    "short_final": self.static.short_final,
                    "avg_adv": self.static.avg_adv,
                    "group": self.static.group,
                    "prev_close": self.static.prev_close,
                    "maxalw": self.static.maxalw
                }
        
        return result
    
    def to_snapshot(self) -> Dict[str, Any]:
        """Lightweight snapshot for UI grids."""
        return {
            "pref_ibkr": self.pref_ibkr,
            "bid": self.l1.bid,
            "ask": self.l1.ask,
            "last": self.l1.last,
            "spread": self.derived.spread,
            "spread_pct": self.derived.spread_percent,
            "ucuzluk": self.scores.bid_buy_ucuzluk,
            "pahalilik": self.scores.ask_sell_pahalilik,
            "bench_chg": self.scores.bench_chg, # NEW
            "qty": self.position.qty,
            "status": self.get_status().value,
            "reason": self.get_missing_reason().value
        }
