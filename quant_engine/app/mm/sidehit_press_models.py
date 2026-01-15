"""
Sidehit Press Models
====================

Pydantic models for Sidehit Press Engine output.
"""

from enum import Enum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime


class EngineMode(str, Enum):
    """Engine operating mode"""
    ANALYSIS_ONLY = "ANALYSIS_ONLY"  # Weekend/market closed - no L1 required
    EXECUTION = "EXECUTION"          # Market open - L1 required for MM signals


class SidehitPressMode(str, Enum):
    """Sidehit valuation influence mode (only for EXECUTION mode)"""
    PASSIVE = "PASSIVE"  # Fbtot/SFStot does NOT affect score
    ACTIVE = "ACTIVE"    # Fbtot/SFStot modifies score


class SignalType(str, Enum):
    """MM signal type (only for EXECUTION mode)"""
    NO_TRADE = "NO_TRADE"
    BUY_FADE = "BUY_FADE"
    SELL_FADE = "SELL_FADE"
    WATCH = "WATCH"


class GroupStatus(str, Enum):
    """Symbol's performance relative to its group"""
    OVERPERFORM_GROUP = "OVERPERFORM_GROUP"
    UNDERPERFORM_GROUP = "UNDERPERFORM_GROUP"
    IN_LINE_WITH_GROUP = "IN_LINE_WITH_GROUP"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class TimeframeVolav(BaseModel):
    """VOLAV data for a single timeframe"""
    timeframe: str
    volav_price: Optional[float] = None
    band_low: Optional[float] = None
    band_high: Optional[float] = None
    dispersion: Optional[float] = None  # band_high - band_low
    tick_count: int = 0
    weighted_volume: float = 0.0


class TimeframeDrift(BaseModel):
    """Drift data between timeframes"""
    drift_15_60: Optional[float] = None    # volav_15m - volav_1h
    drift_60_240: Optional[float] = None   # volav_1h - volav_4h
    drift_240_1d: Optional[float] = None   # volav_4h - volav_1d


class GroupContext(BaseModel):
    """Group-relative analysis"""
    group_id: str
    group_size: int = 0
    
    # Group median drifts
    group_drift_15_60: Optional[float] = None
    group_drift_60_240: Optional[float] = None
    
    # Relative drifts (symbol - group)
    rel_drift_15_60: Optional[float] = None
    rel_drift_60_240: Optional[float] = None
    
    # Status per timeframe
    status_15_60: GroupStatus = GroupStatus.INSUFFICIENT_DATA
    status_60_240: GroupStatus = GroupStatus.INSUFFICIENT_DATA
    
    # Rank within group (percentile)
    group_relative_rank: Optional[float] = None  # 0.0 = worst, 1.0 = best


class AnalysisSummary(BaseModel):
    """Summary fields for ANALYSIS_ONLY mode"""
    strongest_overperform_tf: Optional[str] = None
    strongest_underperform_tf: Optional[str] = None
    drift_consistency_score: int = 0  # Number of TFs aligned in same direction
    overall_drift_direction: Optional[str] = None  # UP, DOWN, MIXED


class ZoneDistance(BaseModel):
    """L1 zone distance (EXECUTION mode only)"""
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None
    mid: Optional[float] = None
    
    # Normalized zone distances
    z_bid_15m: Optional[float] = None  # (bid - volav_15m) / spread
    z_ask_15m: Optional[float] = None  # (ask - volav_15m) / spread
    z_bid_1h: Optional[float] = None
    z_ask_1h: Optional[float] = None


class SidehitFactors(BaseModel):
    """Sidehit influence factors (EXECUTION mode, ACTIVE sidehit)"""
    fbtot: Optional[float] = None
    sfstot: Optional[float] = None
    sidehit_factor: float = 1.0  # Multiplier for MM_SCORE


class SymbolAnalysis(BaseModel):
    """Full analysis output for a symbol"""
    symbol: str
    mode: EngineMode
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # VOLAV per timeframe
    volav_15m: Optional[TimeframeVolav] = None
    volav_1h: Optional[TimeframeVolav] = None
    volav_4h: Optional[TimeframeVolav] = None
    volav_1d: Optional[TimeframeVolav] = None
    
    # Drift
    drift: Optional[TimeframeDrift] = None
    
    # Group context
    group: Optional[GroupContext] = None
    
    # Summary (ANALYSIS_ONLY mode)
    summary: Optional[AnalysisSummary] = None
    
    # Zone distance (EXECUTION mode only)
    zone_distance: Optional[ZoneDistance] = None
    
    # Sidehit factors (EXECUTION mode, ACTIVE sidehit)
    sidehit: Optional[SidehitFactors] = None
    
    # MM Signal (EXECUTION mode only)
    signal_type: SignalType = SignalType.NO_TRADE
    mm_score: Optional[float] = None  # 0-100, only in EXECUTION mode
    
    # Rationale
    rationale: str = ""
    
    # Last 5 Truth Tick Analysis
    last5_tick_avg: Optional[float] = None  # Average/mode price of last 5 truth ticks
    last5_vs_15m: Optional[float] = None    # last5_tick_avg - volav_15m
    last5_vs_1h: Optional[float] = None     # last5_tick_avg - volav_1h
    
    # L1 Data (for Best Odds From Side)
    bid: Optional[float] = None
    ask: Optional[float] = None
    
    # Odd Distance - distance from Son5Tick to Bid/Ask (in cents)
    # Positive odd_bid_distance = Son5Tick is ABOVE bid (good for selling)
    # Positive odd_ask_distance = Ask is ABOVE Son5Tick (good for buying)
    odd_bid_distance: Optional[float] = None   # last5_tick_avg - bid
    odd_ask_distance: Optional[float] = None   # ask - last5_tick_avg
    
    # Debug metrics
    debug_metrics: Dict[str, Any] = Field(default_factory=dict)


class GroupSummary(BaseModel):
    """Summary for a DOS group"""
    group_id: str
    symbol_count: int = 0
    
    # Median drifts
    median_drift_15_60: Optional[float] = None
    median_drift_60_240: Optional[float] = None
    median_drift_240_1d: Optional[float] = None
    
    # Average VOLAVs for group row display
    avg_volav_15m: Optional[float] = None
    avg_volav_1h: Optional[float] = None
    avg_volav_4h: Optional[float] = None
    avg_volav_1d: Optional[float] = None
    
    # Average last 5 tick values
    avg_last5_tick: Optional[float] = None
    avg_last5_vs_15m: Optional[float] = None
    avg_last5_vs_1h: Optional[float] = None
    
    # Symbols in each status
    overperform_symbols: List[str] = Field(default_factory=list)
    underperform_symbols: List[str] = Field(default_factory=list)
    inline_symbols: List[str] = Field(default_factory=list)


class SidehitPressResponse(BaseModel):
    """API response for Sidehit Press"""
    mode: EngineMode
    sidehit_mode: Optional[SidehitPressMode] = None  # Only for EXECUTION
    timestamp: datetime = Field(default_factory=datetime.now)
    symbol_count: int = 0
    group_count: int = 0
    
    # Symbol analyses
    symbols: List[SymbolAnalysis] = Field(default_factory=list)
    
    # Group summaries
    groups: List[GroupSummary] = Field(default_factory=list)
