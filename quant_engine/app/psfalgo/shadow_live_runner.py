"""
Shadow Live Runner - DRY-RUN Operations Orchestrator

Automatically starts/stops RUNALL based on market hours.
Collects session metrics and generates shadow reports.

Key Principles:
- ZERO RISK: dry_run ASLA false yapılmayacak
- NO LOGIC CHANGES: Decision/execution logic'e dokunmaz
- Market-aware: Market open → start, Market close → stop
- Safety guards: Max intents per cycle/day
- Shadow reports: End-of-day summaries

Responsibilities:
- Orchestration (start/stop RUNALL)
- Session metrics collection
- Safety guards (max limits)
- Shadow report generation
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from enum import Enum

from app.core.logger import logger
from app.psfalgo.runall_engine import get_runall_engine, initialize_runall_engine
from app.psfalgo.runall_state_api import get_runall_state_api
from app.psfalgo.decision_models import RunallState
from app.market_data.trading_calendar import TradingCalendar


class SessionStatus(Enum):
    """Shadow session status"""
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    STOPPED = "STOPPED"


@dataclass
class SessionMetrics:
    """
    Daily session metrics for shadow live operations.
    """
    session_date: str  # YYYY-MM-DD
    session_start_time: datetime
    session_end_time: Optional[datetime] = None
    
    # Cycle metrics
    total_cycles: int = 0
    successful_cycles: int = 0
    failed_cycles: int = 0
    
    # Decision metrics
    karbotu_decisions: int = 0
    reducemore_decisions: int = 0
    addnewpos_decisions: int = 0
    total_decisions: int = 0
    total_filtered: int = 0
    
    # Execution metrics
    total_intents: int = 0
    executed_intents: int = 0
    skipped_intents: int = 0
    error_intents: int = 0
    
    # Intent breakdown
    sell_intents: int = 0
    buy_intents: int = 0
    add_intents: int = 0
    
    # Safety guard triggers
    max_intents_per_cycle_hit: int = 0
    max_intents_per_day_hit: bool = False
    
    # Top symbols (by decision count)
    top_symbols: Dict[str, int] = field(default_factory=dict)  # {symbol: decision_count}
    
    # Top filter reasons
    top_filter_reasons: Dict[str, int] = field(default_factory=dict)  # {reason: count}
    
    # Status
    status: str = SessionStatus.IDLE.value
    blocked_reason: Optional[str] = None
    
    def __post_init__(self):
        """Calculate totals"""
        self.total_decisions = (
            self.karbotu_decisions +
            self.reducemore_decisions +
            self.addnewpos_decisions
        )
        self.total_intents = (
            self.executed_intents +
            self.skipped_intents +
            self.error_intents
        )


class ShadowLiveRunner:
    """
    Shadow Live Runner - orchestrates DRY-RUN operations.
    
    Responsibilities:
    1. Market-aware start/stop (market open → start, close → stop)
    2. Session metrics collection
    3. Safety guards (max limits)
    4. Shadow report generation
    
    Does NOT:
    - Modify decision engines
    - Modify execution logic
    - Change dry_run mode (always True)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Shadow Live Runner.
        
        Args:
            config: Configuration dict with:
                - max_intents_per_cycle: Max intents per cycle (default: 20)
                - max_intents_per_day: Max intents per day (default: 300)
                - check_interval_seconds: Market check interval (default: 60)
        """
        self.config = config or {}
        self.max_intents_per_cycle = self.config.get('max_intents_per_cycle', 20)
        self.max_intents_per_day = self.config.get('max_intents_per_day', 300)
        self.check_interval_seconds = self.config.get('check_interval_seconds', 60)
        
        # Trading calendar
        self.trading_calendar = TradingCalendar()
        
        # Current session
        self.current_session: Optional[SessionMetrics] = None
        self.session_date: Optional[str] = None
        
        # Runner state
        self.runner_status = SessionStatus.IDLE
        self.runner_running = False
        self._runner_task: Optional[asyncio.Task] = None
        
        # RUNALL engine
        self.runall_engine: Optional[Any] = None
        
        logger.info(
            f"ShadowLiveRunner initialized: "
            f"max_intents_per_cycle={self.max_intents_per_cycle}, "
            f"max_intents_per_day={self.max_intents_per_day}"
        )
    
    async def start(self):
        """Start shadow live runner"""
        if self.runner_running:
            logger.warning("[SHADOW] Runner already running")
            return
        
        self.runner_running = True
        self.runner_status = SessionStatus.RUNNING
        
        # Initialize RUNALL engine (dry_run=True, ALWAYS)
        if not self.runall_engine:
            self.runall_engine = initialize_runall_engine(config={
                'cycle_interval_seconds': 60,  # 1 minute cycles
                'dry_run_mode': True  # ZERO RISK: Always dry_run
            })
            
            # Connect to State API
            from app.psfalgo.runall_state_api import get_runall_state_api
            state_api = get_runall_state_api()
            if state_api:
                state_api.set_runall_engine(self.runall_engine)
        
        # Start runner loop
        self._runner_task = asyncio.create_task(self._runner_loop())
        
        logger.info("[SHADOW] Shadow Live Runner started")
    
    async def stop(self):
        """Stop shadow live runner"""
        if not self.runner_running:
            return
        
        self.runner_running = False
        self.runner_status = SessionStatus.STOPPED
        
        # Stop RUNALL if running
        if self.runall_engine:
            try:
                await self.runall_engine.stop()
            except Exception as e:
                logger.warning(f"[SHADOW] Error stopping RUNALL: {e}")
        
        # Cancel runner task
        if self._runner_task:
            self._runner_task.cancel()
            try:
                await self._runner_task
            except asyncio.CancelledError:
                pass
        
        # Finalize current session
        if self.current_session:
            self.current_session.session_end_time = datetime.now()
            self.current_session.status = SessionStatus.STOPPED.value
        
        logger.info("[SHADOW] Shadow Live Runner stopped")
    
    async def _runner_loop(self):
        """
        Main runner loop - checks market status and manages RUNALL.
        """
        while self.runner_running:
            try:
                # Check if market is open
                is_market_open = self.trading_calendar.is_market_open()
                
                # Get current date (for session tracking)
                current_date = datetime.now().strftime('%Y-%m-%d')
                
                # Initialize new session if date changed
                if current_date != self.session_date:
                    if self.current_session:
                        # Finalize previous session
                        await self._finalize_session()
                    
                    # Start new session
                    await self._start_new_session(current_date)
                
                # Market open → start RUNALL
                if is_market_open:
                    if self.runner_status != SessionStatus.RUNNING:
                        await self._start_runall()
                else:
                    # Market closed → stop RUNALL
                    if self.runner_status == SessionStatus.RUNNING:
                        await self._stop_runall()
                
                # Collect metrics from current cycle
                await self._collect_cycle_metrics()
                
                # Check safety guards
                await self._check_safety_guards()
                
                # Wait for next check
                await asyncio.sleep(self.check_interval_seconds)
                
            except asyncio.CancelledError:
                logger.info("[SHADOW] Runner loop cancelled")
                break
            except Exception as e:
                logger.error(f"[SHADOW] Error in runner loop: {e}", exc_info=True)
                await asyncio.sleep(5)  # Wait before retry
    
    async def _start_new_session(self, session_date: str):
        """Start new daily session"""
        self.session_date = session_date
        self.current_session = SessionMetrics(
            session_date=session_date,
            session_start_time=datetime.now(),
            status=SessionStatus.IDLE.value
        )
        
        logger.info(f"[SHADOW] New session started: {session_date}")
    
    async def _finalize_session(self):
        """Finalize current session and generate report"""
        if not self.current_session:
            return
        
        self.current_session.session_end_time = datetime.now()
        self.current_session.status = SessionStatus.STOPPED.value
        
        # Generate shadow report
        await self._generate_shadow_report(self.current_session)
        
        logger.info(f"[SHADOW] Session finalized: {self.current_session.session_date}")
    
    async def _start_runall(self):
        """Start RUNALL (if not already running)"""
        if not self.runall_engine:
            return
        
        state = self.runall_engine.get_state()
        if state.get('global_state') == 'RUNNING':
            return  # Already running
        
        try:
            await self.runall_engine.start()
            self.runner_status = SessionStatus.RUNNING
            logger.info("[SHADOW] RUNALL started (market open)")
        except Exception as e:
            logger.error(f"[SHADOW] Error starting RUNALL: {e}", exc_info=True)
    
    async def _stop_runall(self):
        """Stop RUNALL (if running)"""
        if not self.runall_engine:
            return
        
        state = self.runall_engine.get_state()
        if state.get('global_state') != 'RUNNING':
            return  # Not running
        
        try:
            await self.runall_engine.stop()
            self.runner_status = SessionStatus.IDLE
            logger.info("[SHADOW] RUNALL stopped (market closed)")
        except Exception as e:
            logger.error(f"[SHADOW] Error stopping RUNALL: {e}", exc_info=True)
    
    async def _collect_cycle_metrics(self):
        """Collect metrics from current cycle"""
        if not self.current_session or not self.runall_engine:
            return
        
        # Get last cycle decisions from State API
        from app.psfalgo.runall_state_api import get_runall_state_api
        state_api = get_runall_state_api()
        if not state_api:
            return
        
        # Get decision snapshots
        karbotu_snapshot = state_api.get_decision_snapshot('KARBOTU')
        reducemore_snapshot = state_api.get_decision_snapshot('REDUCEMORE')
        addnewpos_snapshot = state_api.get_decision_snapshot('ADDNEWPOS')
        
        # Update decision metrics
        if karbotu_snapshot:
            self.current_session.karbotu_decisions += karbotu_snapshot.total_decisions
            self.current_session.total_filtered += karbotu_snapshot.total_filtered
            
            # Track top symbols
            for decision in karbotu_snapshot.decisions:
                symbol = decision.get('symbol')
                if symbol:
                    self.current_session.top_symbols[symbol] = \
                        self.current_session.top_symbols.get(symbol, 0) + 1
            
            # Track filter reasons
            for filtered in karbotu_snapshot.filtered_out:
                reasons = filtered.get('filter_reasons', [])
                for reason in reasons:
                    self.current_session.top_filter_reasons[reason] = \
                        self.current_session.top_filter_reasons.get(reason, 0) + 1
        
        if reducemore_snapshot:
            self.current_session.reducemore_decisions += reducemore_snapshot.total_decisions
            self.current_session.total_filtered += reducemore_snapshot.total_filtered
        
        if addnewpos_snapshot:
            self.current_session.addnewpos_decisions += addnewpos_snapshot.total_decisions
            self.current_session.total_filtered += addnewpos_snapshot.total_filtered
        
        # Get execution history (last cycle)
        execution_history = state_api.get_execution_history(last_n=1)
        if execution_history:
            last_execution = execution_history[-1]
            self.current_session.total_intents += last_execution.total_intents
            self.current_session.executed_intents += last_execution.executed_count
            self.current_session.skipped_intents += last_execution.skipped_count
            self.current_session.error_intents += last_execution.error_count
            
            # Track intent breakdown
            for intent in last_execution.intents:
                side = intent.get('side')
                if side == 'SELL':
                    self.current_session.sell_intents += 1
                elif side == 'BUY':
                    self.current_session.buy_intents += 1
                elif side == 'ADD':
                    self.current_session.add_intents += 1
        
        # Update cycle count
        state = self.runall_engine.get_state()
        self.current_session.total_cycles = state.get('loop_count', 0)
    
    async def _check_safety_guards(self):
        """Check safety guards and block if limits exceeded"""
        if not self.current_session:
            return
        
        # Check max intents per cycle (from last execution)
        from app.psfalgo.runall_state_api import get_runall_state_api
        state_api = get_runall_state_api()
        if state_api:
            execution_history = state_api.get_execution_history(last_n=1)
            if execution_history:
                last_execution = execution_history[-1]
                if last_execution.total_intents > self.max_intents_per_cycle:
                    self.current_session.max_intents_per_cycle_hit += 1
                    logger.warning(
                        f"[SHADOW] Safety guard: Max intents per cycle exceeded "
                        f"({last_execution.total_intents} > {self.max_intents_per_cycle})"
                    )
                    
                    # Block RUNALL
                    if self.runall_engine:
                        await self.runall_engine.stop()
                        self.runall_engine.global_state = RunallState.BLOCKED
                        self.runner_status = SessionStatus.BLOCKED
                        self.current_session.status = SessionStatus.BLOCKED.value
                        self.current_session.blocked_reason = f"Max intents per cycle exceeded ({last_execution.total_intents})"
        
        # Check max intents per day
        if self.current_session.total_intents > self.max_intents_per_day:
            self.current_session.max_intents_per_day_hit = True
            logger.warning(
                f"[SHADOW] Safety guard: Max intents per day exceeded "
                f"({self.current_session.total_intents} > {self.max_intents_per_day})"
            )
            
            # Block RUNALL
            if self.runall_engine:
                await self.runall_engine.stop()
                self.runall_engine.global_state = RunallState.BLOCKED
                self.runner_status = SessionStatus.BLOCKED
                self.current_session.status = SessionStatus.BLOCKED.value
                self.current_session.blocked_reason = f"Max intents per day exceeded ({self.current_session.total_intents})"
    
    async def _generate_shadow_report(self, session: SessionMetrics):
        """
        Generate end-of-day shadow report.
        
        Args:
            session: SessionMetrics to report on
        """
        report = {
            'session_date': session.session_date,
            'session_start_time': session.session_start_time.isoformat(),
            'session_end_time': session.session_end_time.isoformat() if session.session_end_time else None,
            'session_duration_minutes': (
                (session.session_end_time - session.session_start_time).total_seconds() / 60
                if session.session_end_time else None
            ),
            'status': session.status,
            'blocked_reason': session.blocked_reason,
            'metrics': {
                'cycles': {
                    'total': session.total_cycles,
                    'successful': session.successful_cycles,
                    'failed': session.failed_cycles
                },
                'decisions': {
                    'karbotu': session.karbotu_decisions,
                    'reducemore': session.reducemore_decisions,
                    'addnewpos': session.addnewpos_decisions,
                    'total': session.total_decisions,
                    'filtered': session.total_filtered
                },
                'execution': {
                    'total_intents': session.total_intents,
                    'executed': session.executed_intents,
                    'skipped': session.skipped_intents,
                    'errors': session.error_intents,
                    'execution_rate': (
                        session.executed_intents / session.total_intents * 100
                        if session.total_intents > 0 else 0
                    )
                },
                'intent_breakdown': {
                    'sell': session.sell_intents,
                    'buy': session.buy_intents,
                    'add': session.add_intents
                },
                'safety_guards': {
                    'max_intents_per_cycle_hit': session.max_intents_per_cycle_hit,
                    'max_intents_per_day_hit': session.max_intents_per_day_hit
                }
            },
            'top_symbols': dict(sorted(
                session.top_symbols.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]),  # Top 10
            'top_filter_reasons': dict(sorted(
                session.top_filter_reasons.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10])  # Top 10
        }
        
        # Save report to file
        from pathlib import Path
        reports_dir = Path('quant_engine/reports/shadow')
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        report_file = reports_dir / f"shadow_report_{session.session_date}.json"
        import json
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        # Generate human-readable report
        await self._generate_human_readable_report(session, report_file)
        
        logger.info(f"[SHADOW] Shadow report generated: {report_file}")
    
    async def _generate_human_readable_report(self, session: SessionMetrics, json_file: Path):
        """Generate human-readable shadow report"""
        report_file = json_file.with_suffix('.txt')
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"SHADOW LIVE REPORT - {session.session_date}\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"Session Duration: {session.session_start_time.strftime('%H:%M:%S')} - ")
            if session.session_end_time:
                f.write(f"{session.session_end_time.strftime('%H:%M:%S')}\n")
            else:
                f.write("ONGOING\n")
            f.write(f"Status: {session.status}\n")
            if session.blocked_reason:
                f.write(f"Blocked Reason: {session.blocked_reason}\n")
            f.write("\n")
            
            f.write("CYCLE METRICS\n")
            f.write("-" * 80 + "\n")
            f.write(f"Total Cycles: {session.total_cycles}\n")
            f.write(f"Successful: {session.successful_cycles}\n")
            f.write(f"Failed: {session.failed_cycles}\n")
            f.write("\n")
            
            f.write("DECISION METRICS\n")
            f.write("-" * 80 + "\n")
            f.write(f"KARBOTU: {session.karbotu_decisions}\n")
            f.write(f"REDUCEMORE: {session.reducemore_decisions}\n")
            f.write(f"ADDNEWPOS: {session.addnewpos_decisions}\n")
            f.write(f"Total Decisions: {session.total_decisions}\n")
            f.write(f"Total Filtered: {session.total_filtered}\n")
            f.write("\n")
            
            f.write("EXECUTION METRICS\n")
            f.write("-" * 80 + "\n")
            f.write(f"Total Intents: {session.total_intents}\n")
            f.write(f"Executed: {session.executed_intents}\n")
            f.write(f"Skipped: {session.skipped_intents}\n")
            f.write(f"Errors: {session.error_intents}\n")
            if session.total_intents > 0:
                execution_rate = session.executed_intents / session.total_intents * 100
                f.write(f"Execution Rate: {execution_rate:.2f}%\n")
            f.write("\n")
            
            f.write("INTENT BREAKDOWN\n")
            f.write("-" * 80 + "\n")
            f.write(f"SELL: {session.sell_intents}\n")
            f.write(f"BUY: {session.buy_intents}\n")
            f.write(f"ADD: {session.add_intents}\n")
            f.write("\n")
            
            f.write("SAFETY GUARDS\n")
            f.write("-" * 80 + "\n")
            f.write(f"Max Intents Per Cycle Hit: {session.max_intents_per_cycle_hit}\n")
            f.write(f"Max Intents Per Day Hit: {session.max_intents_per_day_hit}\n")
            f.write("\n")
            
            f.write("TOP 10 SYMBOLS (by decision count)\n")
            f.write("-" * 80 + "\n")
            top_symbols = sorted(session.top_symbols.items(), key=lambda x: x[1], reverse=True)[:10]
            for symbol, count in top_symbols:
                f.write(f"  {symbol}: {count}\n")
            f.write("\n")
            
            f.write("TOP 10 FILTER REASONS\n")
            f.write("-" * 80 + "\n")
            top_reasons = sorted(session.top_filter_reasons.items(), key=lambda x: x[1], reverse=True)[:10]
            for reason, count in top_reasons:
                f.write(f"  {reason}: {count}\n")
            f.write("\n")
            
            f.write("=" * 80 + "\n")
            f.write("END OF REPORT\n")
            f.write("=" * 80 + "\n")
        
        logger.info(f"[SHADOW] Human-readable report generated: {report_file}")
    
    def get_current_session_metrics(self) -> Optional[SessionMetrics]:
        """Get current session metrics"""
        return self.current_session


# Global instance
_shadow_live_runner: Optional[ShadowLiveRunner] = None


def get_shadow_live_runner() -> Optional[ShadowLiveRunner]:
    """Get global ShadowLiveRunner instance"""
    return _shadow_live_runner


def initialize_shadow_live_runner(config: Optional[Dict[str, Any]] = None) -> ShadowLiveRunner:
    """Initialize global ShadowLiveRunner instance"""
    global _shadow_live_runner
    _shadow_live_runner = ShadowLiveRunner(config=config)
    logger.info("ShadowLiveRunner initialized")
    return _shadow_live_runner






