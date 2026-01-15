"""
Market Snapshot Models - Scanner Layer

Data models for market snapshot (single source of truth for decision engines).
Janall-compatible structure with daily snapshot logic.

Key Principles:
- SADECE hesaplar ve saklar
- Karar vermez
- Execution yapmaz
- Decision engine'ler için TEK GERÇEK VERİ KAYNAĞI
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any


@dataclass
class MarketSnapshot:
    """
    Market Snapshot - single source of truth for decision engines.
    
    Janall-compatible structure:
    - Live market data (bid/ask/last/spread)
    - Daily snapshot data (befday_*)
    - Computed metrics (SMA63_CHG, FBTOT, GORT, etc.)
    - Account type (IBKR_GUN / IBKR_PED)
    """
    # Symbol
    symbol: str
    
    # Live market data
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    spread: Optional[float] = None
    spread_percent: Optional[float] = None
    prev_close: Optional[float] = None
    
    # Daily snapshot (befday_* - from previous day close)
    befday_qty: float = 0.0  # Quantity at previous day close
    befday_cost: float = 0.0  # Cost at previous day close
    
    # Today changes (calculated from current position vs befday)
    today_qty_chg: float = 0.0  # today_qty - befday_qty
    today_cost: float = 0.0  # Current cost (today_qty * current_price)
    
    # Computed metrics (Janall-compatible)
    sma63_chg: Optional[float] = None  # SMA63 change
    sma246_chg: Optional[float] = None  # SMA246 change
    fbtot: Optional[float] = None  # Front Buy Total
    sfstot: Optional[float] = None  # Short Front Sell Total
    gort: Optional[float] = None  # Group-relative value
    avg_adv: Optional[float] = None  # Average Daily Volume
    
    # Pricing overlay scores (ucuzluk/pahalılık skorları)
    bb_ucuz: Optional[float] = None  # Bid Buy Ucuzluk Skoru
    fb_ucuz: Optional[float] = None  # Front Buy Ucuzluk Skoru
    ab_ucuz: Optional[float] = None  # Ask Buy Ucuzluk Skoru
    as_pahali: Optional[float] = None  # Ask Sell Pahalılık Skoru
    fs_pahali: Optional[float] = None  # Front Sell Pahalılık Skoru
    bs_pahali: Optional[float] = None  # Bid Sell Pahalılık Skoru
    
    # Final scores (from pricing overlay)
    final_bb: Optional[float] = None  # Final Bid Buy
    final_fb: Optional[float] = None  # Final Front Buy
    final_ab: Optional[float] = None  # Final Ask Buy
    final_as: Optional[float] = None  # Final Ask Sell
    final_fs: Optional[float] = None  # Final Front Sell
    final_bs: Optional[float] = None  # Final Bid Sell
    final_sas: Optional[float] = None  # Final Short Ask Sell
    
    # Benchmark metrics
    benchmark_chg: Optional[float] = None  # Benchmark change
    pricing_mode: Optional[str] = None  # Pricing mode: "RELATIVE" or "ABSOLUTE"
    
    # Static data (from CSV)
    final_thg: Optional[float] = None  # FINAL_THG from static data
    short_final: Optional[float] = None  # SHORT_FINAL from static data
    
    # Account type (for snapshot separation)
    account_type: Optional[str] = None  # "IBKR_GUN" or "IBKR_PED"
    
    # Timestamp
    snapshot_ts: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for JSON serialization"""
        return {
            'symbol': self.symbol,
            'bid': self.bid,
            'ask': self.ask,
            'last': self.last,
            'spread': self.spread,
            'spread_percent': self.spread_percent,
            'prev_close': self.prev_close,
            'befday_qty': self.befday_qty,
            'befday_cost': self.befday_cost,
            'today_qty_chg': self.today_qty_chg,
            'today_cost': self.today_cost,
            'sma63_chg': self.sma63_chg,
            'sma246_chg': self.sma246_chg,
            'fbtot': self.fbtot,
            'sfstot': self.sfstot,
            'gort': self.gort,
            'avg_adv': self.avg_adv,
            'bb_ucuz': self.bb_ucuz,
            'fb_ucuz': self.fb_ucuz,
            'ab_ucuz': self.ab_ucuz,
            'as_pahali': self.as_pahali,
            'fs_pahali': self.fs_pahali,
            'bs_pahali': self.bs_pahali,
            'final_bb': self.final_bb,
            'final_fb': self.final_fb,
            'final_ab': self.final_ab,
            'final_as': self.final_as,
            'final_fs': self.final_fs,
            'final_bs': self.final_bs,
            'final_sas': self.final_sas,
            'benchmark_chg': self.benchmark_chg,
            'final_thg': self.final_thg,
            'short_final': self.short_final,
            'account_type': self.account_type,
            'snapshot_ts': self.snapshot_ts.isoformat()
        }
    
    def to_scanner_row(self) -> Dict[str, Any]:
        """Convert to scanner row format (for UI/API)"""
        return {
            'PREF_IBKR': self.symbol,
            'Bid': self.bid,
            'Ask': self.ask,
            'Last': self.last,
            'Spread': self.spread,
            'Spread %': self.spread_percent,
            'Prev Close': self.prev_close,
            'Befday Qty': self.befday_qty,
            'Befday Cost': self.befday_cost,
            'Today Qty Chg': self.today_qty_chg,
            'Today Cost': self.today_cost,
            'SMA63 CHG': self.sma63_chg,
            'SMA246 CHG': self.sma246_chg,
            'FBTOT': self.fbtot,
            'SFSTOT': self.sfstot,
            'GORT': self.gort,
            'AVG_ADV': self.avg_adv,
            'BB_UCUZ': self.bb_ucuz,
            'FB_UCUZ': self.fb_ucuz,
            'AB_UCUZ': self.ab_ucuz,
            'AS_PAHALI': self.as_pahali,
            'FS_PAHALI': self.fs_pahali,
            'BS_PAHALI': self.bs_pahali,
            'FINAL_BB': self.final_bb,
            'FINAL_FB': self.final_fb,
            'FINAL_AB': self.final_ab,
            'FINAL_AS': self.final_as,
            'FINAL_FS': self.final_fs,
            'FINAL_BS': self.final_bs,
            'FINAL_SAS': self.final_sas,
            'BENCHMARK_CHG': self.benchmark_chg,
            'FINAL_THG': self.final_thg,
            'SHORT_FINAL': self.short_final,
            'Account Type': self.account_type,
            'Snapshot TS': self.snapshot_ts.isoformat()
        }


