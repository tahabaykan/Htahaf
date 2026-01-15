"""
Greatest MM Quant Models
========================

Data models for the Greatest MM Quant scoring system.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class MMScenarioType(str, Enum):
    """Type of MM scenario"""
    ORIGINAL = "ORIGINAL"           # Entry=Bid/Ask±spread×0.15, Son5Tick=current
    NEW_SON5 = "NEW_SON5"           # Entry same, Son5Tick=new_print
    NEW_ENTRY = "NEW_ENTRY"         # Entry=new_print±0.01, Son5Tick=old
    BOTH_NEW = "BOTH_NEW"           # Entry=old_son5±0.01, Son5Tick=new_print


class MMScenario(BaseModel):
    """Single MM scenario result"""
    scenario_type: MMScenarioType
    
    # Entry points
    entry_long: float
    entry_short: float
    son5_tick: float
    
    # Distances
    b_long: float       # Son5Tick - Entry_Long
    a_long: float       # Ask - Son5Tick
    a_short: float      # Entry_Short - Son5Tick
    b_short: float      # Son5Tick - Bid
    
    # Ucuzluk/Pahalılık
    ucuzluk: float
    pahalilik: float
    
    # Final MM Scores
    mm_long: float
    mm_short: float
    
    # Is above threshold?
    long_valid: bool = False    # mm_long >= 30
    short_valid: bool = False   # mm_short >= 30


class MMAnalysis(BaseModel):
    """Complete MM analysis for a symbol"""
    symbol: str
    timestamp: datetime = Field(default_factory=datetime.now)
    
    # Market data
    bid: Optional[float] = None
    ask: Optional[float] = None
    spread: Optional[float] = None
    prev_close: Optional[float] = None
    benchmark_chg: Optional[float] = None
    
    # Son5Tick data
    son5_tick: Optional[float] = None
    new_print: Optional[float] = None
    has_new_print: bool = False
    
    # 4 Scenarios (or 1 if no new_print)
    scenarios: List[MMScenario] = Field(default_factory=list)
    
    # Best entry recommendations (where MM score closest to 30 but >= 30)
    best_long_entry: Optional[float] = None
    best_long_scenario: Optional[MMScenarioType] = None
    best_long_score: Optional[float] = None
    
    best_short_entry: Optional[float] = None
    best_short_scenario: Optional[MMScenarioType] = None
    best_short_score: Optional[float] = None
    
    # Status
    long_actionable: bool = False   # At least one scenario has mm_long >= 30
    short_actionable: bool = False  # At least one scenario has mm_short >= 30
    
    # Debug
    tick_count: int = 0
    error: Optional[str] = None


class MMWatchlistItem(BaseModel):
    """Symbol in Greatest MM watchlist"""
    symbol: str
    added_at: datetime = Field(default_factory=datetime.now)
    last_updated: datetime = Field(default_factory=datetime.now)
    
    # Current state
    son5_tick: Optional[float] = None
    new_print: Optional[float] = None
    
    # Latest analysis
    latest_analysis: Optional[MMAnalysis] = None
    
    # Orders placed
    long_order_placed: bool = False
    long_order_price: Optional[float] = None
    short_order_placed: bool = False
    short_order_price: Optional[float] = None


class GreatestMMResponse(BaseModel):
    """API response for Greatest MM analysis"""
    success: bool
    timestamp: datetime = Field(default_factory=datetime.now)
    symbol_count: int = 0
    actionable_count: int = 0  # Symbols with at least one valid entry
    analyses: List[MMAnalysis] = Field(default_factory=list)
    error: Optional[str] = None
