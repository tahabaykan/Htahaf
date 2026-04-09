"""
Cycle Reporter - Cycle-based summary reporting for all symbols

Instead of logging every decision individually (expensive for 440 stocks),
this service creates a comprehensive summary report at the end of each cycle.

Features:
- Per-symbol status (SENT, BLOCKED, SKIPPED)
- Aggregated statistics
- Overwrite mode (only keep latest cycle)
- Console summary (not per-symbol spam)
- File-based storage (cycle_latest.json)
- API accessible

Example:
    cycle_reporter.start_cycle("2026-01-18T18:55:00")
    
    # During cycle
    cycle_reporter.record_symbol_status(
        symbol='SOJD',
        engine='KARBOTU_V2',
        status='SENT',
        action='SELL',
        qty=500,
        reason='Step 2: FBTOT < 1.10'
    )
    
    cycle_reporter.record_symbol_status(
        symbol='XYZ',
        engine='KARBOTU_V2',
        status='BLOCKED',
        reason='MAXALW_EXCEEDED'
    )
    
    # End of cycle
    cycle_reporter.end_cycle()
"""
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from enum import Enum

from loguru import logger


class SymbolStatus(Enum):
    """Status of symbol in cycle"""
    SENT = "SENT"               # Order sent
    BLOCKED = "BLOCKED"         # Order blocked by limit/filter
    SKIPPED = "SKIPPED"         # Not analyzed (no signal)
    ADJUSTED = "ADJUSTED"       # Quantity adjusted
    PENDING = "PENDING"         # Has pending orders
    NO_POSITION = "NO_POSITION" # Not in portfolio


@dataclass
class SymbolReport:
    """Report for a single symbol"""
    symbol: str
    status: str  # SENT, BLOCKED, SKIPPED, etc.
    engine: Optional[str] = None  # Which engine made decision
    
    # Order info (if SENT)
    action: Optional[str] = None  # BUY, SELL
    qty: Optional[int] = None
    price: Optional[float] = None
    tag: Optional[str] = None
    
    # Blocking info (if BLOCKED)
    block_reason: Optional[str] = None
    
    # Context
    current_qty: Optional[int] = None
    befday_qty: Optional[int] = None
    maxalw: Optional[int] = None
    pending_orders: int = 0
    
    # Metrics (if available)
    fbtot: Optional[float] = None
    sfstot: Optional[float] = None
    gort: Optional[float] = None
    
    # Human-readable reason
    reason: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class CycleSummary:
    """Summary of entire cycle"""
    cycle_id: str
    start_time: str
    end_time: str
    duration_seconds: float
    
    # Statistics
    total_symbols: int = 0
    sent_count: int = 0
    blocked_count: int = 0
    skipped_count: int = 0
    adjusted_count: int = 0
    
    # By engine
    engine_stats: Dict[str, Dict[str, int]] = field(default_factory=dict)
    
    # Block reasons breakdown
    block_reasons: Dict[str, int] = field(default_factory=dict)
    
    # Symbol reports
    symbols: Dict[str, SymbolReport] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            'cycle_id': self.cycle_id,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'duration_seconds': self.duration_seconds,
            'total_symbols': self.total_symbols,
            'sent_count': self.sent_count,
            'blocked_count': self.blocked_count,
            'skipped_count': self.skipped_count,
            'adjusted_count': self.adjusted_count,
            'engine_stats': self.engine_stats,
            'block_reasons': self.block_reasons,
            'symbols': {sym: rep.to_dict() for sym, rep in self.symbols.items()}
        }


class CycleReporter:
    """
    Cycle-based summary reporter
    
    Collects all symbol decisions during a cycle and generates
    a comprehensive summary report at the end.
    
    Overwrites previous cycle report (only keeps latest).
    """
    
    def __init__(self, output_dir: str = "cycle_reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.current_cycle: Optional[CycleSummary] = None
        self.cycle_start_time: Optional[datetime] = None
        
        logger.info(f"[CycleReporter] Initialized (output: {self.output_dir})")
    
    def start_cycle(self, cycle_id: str):
        """Start a new cycle"""
        self.cycle_start_time = datetime.now()
        self.current_cycle = CycleSummary(
            cycle_id=cycle_id,
            start_time=self.cycle_start_time.isoformat(),
            end_time="",
            duration_seconds=0.0
        )
        logger.info(f"[CycleReporter] Started cycle: {cycle_id}")
    
    def record_symbol_status(
        self,
        symbol: str,
        status: SymbolStatus,
        engine: Optional[str] = None,
        action: Optional[str] = None,
        qty: Optional[int] = None,
        price: Optional[float] = None,
        tag: Optional[str] = None,
        block_reason: Optional[str] = None,
        reason: Optional[str] = None,
        current_qty: Optional[int] = None,
        befday_qty: Optional[int] = None,
        maxalw: Optional[int] = None,
        pending_orders: int = 0,
        fbtot: Optional[float] = None,
        sfstot: Optional[float] = None,
        gort: Optional[float] = None
    ):
        """Record status for a symbol"""
        if not self.current_cycle:
            logger.warning("[CycleReporter] No active cycle, cannot record")
            return
        
        report = SymbolReport(
            symbol=symbol,
            status=status.value,
            engine=engine,
            action=action,
            qty=qty,
            price=price,
            tag=tag,
            block_reason=block_reason,
            reason=reason,
            current_qty=current_qty,
            befday_qty=befday_qty,
            maxalw=maxalw,
            pending_orders=pending_orders,
            fbtot=fbtot,
            sfstot=sfstot,
            gort=gort
        )
        
        self.current_cycle.symbols[symbol] = report
        
        # Update statistics
        self.current_cycle.total_symbols = len(self.current_cycle.symbols)
        
        if status == SymbolStatus.SENT:
            self.current_cycle.sent_count += 1
        elif status == SymbolStatus.BLOCKED:
            self.current_cycle.blocked_count += 1
            if block_reason:
                self.current_cycle.block_reasons[block_reason] = \
                    self.current_cycle.block_reasons.get(block_reason, 0) + 1
        elif status == SymbolStatus.SKIPPED:
            self.current_cycle.skipped_count += 1
        elif status == SymbolStatus.ADJUSTED:
            self.current_cycle.adjusted_count += 1
        
        # Engine stats
        if engine:
            if engine not in self.current_cycle.engine_stats:
                self.current_cycle.engine_stats[engine] = {
                    'sent': 0, 'blocked': 0, 'skipped': 0, 'adjusted': 0
                }
            
            if status == SymbolStatus.SENT:
                self.current_cycle.engine_stats[engine]['sent'] += 1
            elif status == SymbolStatus.BLOCKED:
                self.current_cycle.engine_stats[engine]['blocked'] += 1
            elif status == SymbolStatus.SKIPPED:
                self.current_cycle.engine_stats[engine]['skipped'] += 1
            elif status == SymbolStatus.ADJUSTED:
                self.current_cycle.engine_stats[engine]['adjusted'] += 1
    
    def end_cycle(self) -> Optional[CycleSummary]:
        """End cycle and generate report"""
        if not self.current_cycle:
            logger.warning("[CycleReporter] No active cycle to end")
            return None
        
        # Finalize timing
        end_time = datetime.now()
        self.current_cycle.end_time = end_time.isoformat()
        self.current_cycle.duration_seconds = (end_time - self.cycle_start_time).total_seconds()
        
        # Log summary to console
        self._log_summary()
        
        # Save to file (overwrite mode)
        self._save_to_file()
        
        summary = self.current_cycle
        self.current_cycle = None
        
        return summary
    
    def _log_summary(self):
        """Log cycle summary to console"""
        cycle = self.current_cycle
        
        logger.info("=" * 80)
        logger.info(f"[CYCLE SUMMARY] {cycle.cycle_id}")
        logger.info(f"  Duration: {cycle.duration_seconds:.2f}s")
        logger.info(f"  Total Symbols: {cycle.total_symbols}")
        logger.info(f"  ✅ SENT: {cycle.sent_count}")
        logger.info(f"  ❌ BLOCKED: {cycle.blocked_count}")
        logger.info(f"  ⚠️ ADJUSTED: {cycle.adjusted_count}")
        logger.info(f"  🔍 SKIPPED: {cycle.skipped_count}")
        
        # Engine breakdown
        if cycle.engine_stats:
            logger.info("")
            logger.info("  Engine Breakdown:")
            for engine, stats in cycle.engine_stats.items():
                logger.info(
                    f"    {engine}: "
                    f"SENT={stats['sent']}, "
                    f"BLOCKED={stats['blocked']}, "
                    f"ADJUSTED={stats['adjusted']}, "
                    f"SKIPPED={stats['skipped']}"
                )
        
        # Top block reasons
        if cycle.block_reasons:
            logger.info("")
            logger.info("  Top Block Reasons:")
            sorted_reasons = sorted(
                cycle.block_reasons.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]
            for reason, count in sorted_reasons:
                logger.info(f"    {reason}: {count}")
        
        logger.info("=" * 80)
    
    def _save_to_file(self):
        """Save to file (overwrite mode)"""
        try:
            # Save as cycle_latest.json (always overwrite)
            latest_path = self.output_dir / "cycle_latest.json"
            with open(latest_path, 'w', encoding='utf-8') as f:
                json.dump(self.current_cycle.to_dict(), f, indent=2, ensure_ascii=False)
            
            logger.info(f"[CycleReporter] Saved to {latest_path}")
            
            # Also save with timestamp for debugging (keep last 10)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            timestamped_path = self.output_dir / f"cycle_{timestamp}.json"
            with open(timestamped_path, 'w', encoding='utf-8') as f:
                json.dump(self.current_cycle.to_dict(), f, indent=2, ensure_ascii=False)
            
            # Cleanup old files (keep last 10)
            self._cleanup_old_reports()
        
        except Exception as e:
            logger.error(f"[CycleReporter] Error saving report: {e}", exc_info=True)
    
    def _cleanup_old_reports(self):
        """Keep only last 10 timestamped reports"""
        try:
            reports = sorted(self.output_dir.glob("cycle_*.json"))
            # Exclude cycle_latest.json
            reports = [r for r in reports if r.name != "cycle_latest.json"]
            
            if len(reports) > 10:
                for old_report in reports[:-10]:
                    old_report.unlink()
                    logger.debug(f"[CycleReporter] Deleted old report: {old_report.name}")
        
        except Exception as e:
            logger.error(f"[CycleReporter] Error cleaning up reports: {e}")
    
    def get_latest_report(self) -> Optional[Dict]:
        """Get latest cycle report"""
        try:
            latest_path = self.output_dir / "cycle_latest.json"
            if latest_path.exists():
                with open(latest_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"[CycleReporter] Error reading latest report: {e}")
        
        return None
    
    def get_symbol_report(self, symbol: str) -> Optional[Dict]:
        """Get report for specific symbol from latest cycle"""
        latest = self.get_latest_report()
        if latest and 'symbols' in latest:
            return latest['symbols'].get(symbol)
        return None


# Global instance
_cycle_reporter: Optional[CycleReporter] = None


def get_cycle_reporter() -> CycleReporter:
    """Get global cycle reporter instance"""
    global _cycle_reporter
    if _cycle_reporter is None:
        _cycle_reporter = CycleReporter()
    return _cycle_reporter


def initialize_cycle_reporter(output_dir: Optional[str] = None):
    """Initialize global cycle reporter"""
    global _cycle_reporter
    _cycle_reporter = CycleReporter(output_dir=output_dir or "cycle_reports")
    logger.info("[CycleReporter] Global instance initialized")
    return _cycle_reporter
