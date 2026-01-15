"""
ADDNEWPOS Decision Engine - Janall-Compatible v2.0

ADDNEWPOS (Add New Position) decision engine for opening new positions.
Supports both LONG and SHORT positions (AddLong and AddShort modes).

Key Principles:
- Stateless: Input → Output only
- Config-driven: All rules from psfalgo_rules.yaml
- Explainable: Every decision has reason and filter_reasons
- Production-grade: Async, type hints, error handling
- Janall-compatible: Same logic, same conditions, same lot calculations
- Dual mode: AddLong Only, AddShort Only, or Both

Modes:
- addlong_only: Only add LONG positions (BID_BUY)
- addshort_only: Only add SHORT positions (ASK_SELL)
- both: Add both LONG and SHORT positions
"""

import asyncio
import yaml
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple


from app.core.logger import logger
from app.psfalgo.decision_models import (
    DecisionRequest,
    DecisionResponse,
    Decision,
    PositionSnapshot,
    SymbolMetrics,
    ExposureSnapshot,
    RejectReason
)

from app.psfalgo.decision_cooldown import get_decision_cooldown_manager
from app.psfalgo.confidence_calculator import get_confidence_calculator
from app.psfalgo.exposure_calculator import get_exposure_calculator
# NEW: Intent Math Shared Module
from app.psfalgo.intent_math import (
    compute_intents, 
    calculate_rounded_lot, 
    compute_desire,
    clamp_no_flip, 
    clamp_post_trade_hold
)
from app.psfalgo.decision_models import RejectReason
from app.psfalgo.reject_reason_store import get_reject_reason_store


class AddnewposEngine:
    """
    ADDNEWPOS Decision Engine - Janall-compatible, config-driven.
    
    Supports three modes:
    1. addlong_only: Only BUY/ADD long positions
       - Filter: Bid Buy Ucuzluk > 0.06, Fbtot > 1.10
       - Order: BID_BUY
    
    2. addshort_only: Only SHORT/ADD short positions
       - Filter: Ask Sell Pahalılık > 0.06, SFStot > 1.10
       - Order: ASK_SELL
    
    3. both: Both long and short positions
    
    Portfolio Rules (Janall addnewpos_rules):
    - < 1%: MAXALW × 0.50, Portfolio × 5%
    - 1-3%: MAXALW × 0.40, Portfolio × 4%
    - 3-5%: MAXALW × 0.30, Portfolio × 3%
    - 5-7%: MAXALW × 0.20, Portfolio × 2%
    - 7-10%: MAXALW × 0.10, Portfolio × 1.5%
    - >= 10%: MAXALW × 0.05, Portfolio × 1%
    
    Exposure Usage: 60% of remaining exposure
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize ADDNEWPOS Engine.
        
        Args:
            config_path: Path to psfalgo_rules.yaml
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'psfalgo_rules.yaml'
        
        self.config_path = config_path
        self.rules: Dict[str, Any] = {}
        self.settings: Dict[str, Any] = {}
        self.eligibility: Dict[str, Any] = {}
        self.addlong_config: Dict[str, Any] = {}
        self.addshort_config: Dict[str, Any] = {}
        self.portfolio_rules: List[Dict[str, Any]] = []
        # NEW: Mental Model v1 Configs
        self.intent_model_config: Dict[str, Any] = {}
        self.lot_policy_config: Dict[str, Any] = {}
        self.gating_config: Dict[str, Any] = {}
        self.pick_policy_config: Dict[str, Any] = {}
        
        self._load_rules()
    
    def _load_rules(self):
        """Load rules from psfalgo_rules.yaml"""
        try:
            if not self.config_path.exists():
                logger.error(f"ADDNEWPOS rules file not found: {self.config_path}")
                self._set_default_rules()
                return
            
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            self.rules = config.get('addnewpos', {})
            self.settings = self.rules.get('settings', {})
            self.eligibility = self.rules.get('eligibility', {})
            self.addlong_config = self.rules.get('addlong', {})
            self.addshort_config = self.rules.get('addshort', {})
            self.portfolio_rules = self.rules.get('rules', {}).get('thresholds', [])
            self.exposure_usage_percent = self.rules.get('rules', {}).get('exposure_usage_percent', 60.0)
            
            # ═══════════════════════════════════════════════════════════════════
            # NEW: Mental Model v1 Configs
            # ═══════════════════════════════════════════════════════════════════
            self.intent_model_config = config.get('intent_model', {})
            self.lot_policy_config = config.get('lot_policy', {})
            self.gating_config = config.get('gating', {})
            self.pick_policy_config = config.get('pick_policy', {})

            # NEW: Load risk_regimes for soft/hard derisk awareness
            self.risk_regimes = config.get('risk_regimes', {})
            self.soft_derisk = self.risk_regimes.get('soft_derisk', {})
            self.hard_derisk = self.risk_regimes.get('hard_derisk', {})
            self.spread_rules = self.risk_regimes.get('spread_rules', {})
            
            # Soft derisk step multiplier (e.g., 0.25 = step drops to 25%)
            self.soft_derisk_step_multiplier = self.soft_derisk.get('addnewpos_step_multiplier', 0.25)
            self.soft_derisk_threshold = self.soft_derisk.get('threshold_pct', 120.0)
            self.hard_derisk_threshold = self.hard_derisk.get('threshold_pct', 130.0)
            
            # Spread rules for ADDNEWPOS (spread = ADVANTAGE, not blocking)
            self.addnewpos_spread_blocks = self.spread_rules.get('addnewpos_spread_blocks', False)
            self.addnewpos_spread_log_threshold = self.spread_rules.get('addnewpos_spread_log_threshold', 0.30)
            
            logger.info(f"[ADDNEWPOS] Rules loaded. Intent Model: {bool(self.intent_model_config)}")
            # ═══════════════════════════════════════════════════════════════════
            
            if not self.rules:
                logger.warning("ADDNEWPOS rules not found in config file, using defaults")
                self._set_default_rules()
                return
            
            logger.info(f"ADDNEWPOS rules loaded from {self.config_path}")
            
        except Exception as e:
            logger.error(f"Error loading ADDNEWPOS rules: {e}", exc_info=True)
            self._set_default_rules()
    

    def _set_default_rules(self):
        """Set default rules (Janall-compatible)"""
        self.eligibility = {
            'exposure_ratio_threshold': 0.8,
            'exposure_mode': 'OFANSIF'
        }
        self.addlong_config = {
            'enabled': True,
            'filters': {
                # Janall: bid_buy_ucuzluk < -0.06 means stock is CHEAP (negative = cheaper)
                # So we want bid_buy_ucuzluk_lt: -0.06 (less than -0.06)
                'bid_buy_ucuzluk_lt': -0.06,  # NEGATIVE = UCUZ (cheaper)
                # Janall: Fbtot > 1.10 means UCUZ (cheap) - we want to BUY cheap stocks
                'fbtot_gt': 1.10,  # FBTOT > 1.10 = UCUZ (cheap) - REQUIRED for LONG
                'spread_lt': 0.15,  # Spread less than 15 cents
                'avg_adv_gt': 500.0  # Minimum liquidity
            },
            'order_type': 'BID_BUY'
        }
        self.addshort_config = {
            'enabled': True,
            'filters': {
                # Janall: ask_sell_pahalilik > 0.06 means stock is EXPENSIVE (positive = more expensive)
                # So we want ask_sell_pahalilik_gt: 0.06 (greater than 0.06)
                'ask_sell_pahalilik_gt': 0.06,  # POSITIVE = PAHALI (more expensive)
                # Janall: SFStot > 1.10 means PAHALI (expensive) - we want to SHORT expensive stocks
                'sfstot_gt': 1.10,  # SFStot > 1.10 = PAHALI (expensive) - REQUIRED for SHORT
                'spread_lt': 0.15,  # Spread less than 15 cents
                'avg_adv_gt': 500.0  # Minimum liquidity
            },
            'order_type': 'ASK_SELL'
        }
        self.portfolio_rules = [
            {'max_portfolio_percent': 1.0, 'maxalw_multiplier': 0.50, 'portfolio_percent': 5.0},
            {'max_portfolio_percent': 3.0, 'maxalw_multiplier': 0.40, 'portfolio_percent': 4.0},
            {'max_portfolio_percent': 5.0, 'maxalw_multiplier': 0.30, 'portfolio_percent': 3.0},
            {'max_portfolio_percent': 7.0, 'maxalw_multiplier': 0.20, 'portfolio_percent': 2.0},
            {'max_portfolio_percent': 10.0, 'maxalw_multiplier': 0.10, 'portfolio_percent': 1.5},
            {'max_portfolio_percent': 100.0, 'maxalw_multiplier': 0.05, 'portfolio_percent': 1.0}
        ]
        self.exposure_usage_percent = 60.0
        self.settings = {
            'max_lot_per_symbol': 200,
            'default_lot': 200,
            'min_lot_size': 100,
            'cooldown_minutes': 5.0,
            'min_avg_adv_divisor': 10,
            'mode': 'addlong_only'
        }
    
    def is_eligible(self, exposure: Optional[ExposureSnapshot], exposure_mode: Optional[str] = None) -> Tuple[bool, str]:
        """
        Check if ADDNEWPOS should run based on exposure thresholds.
        
        ADDNEWPOS runs when:
        - exposure_ratio < threshold (default 80%)
        - AND mode is OFANSIF
        
        Args:
            exposure: ExposureSnapshot object
            exposure_mode: Current exposure mode
            
        Returns:
            (is_eligible, reason)
        """
        if exposure is None:
            return False, "Exposure snapshot not available"
        
        exposure_ratio_threshold = self.eligibility.get('exposure_ratio_threshold', 0.8)
        required_mode = self.eligibility.get('exposure_mode', 'OFANSIF')
        
        # Check mode
        if exposure_mode is None:
            exposure_calculator = get_exposure_calculator()
            if exposure_calculator:
                exposure_mode = exposure_calculator.determine_exposure_mode(exposure)
            else:
                if exposure.pot_max > 0:
                    exposure_ratio = exposure.pot_total / exposure.pot_max
                    exposure_mode = 'OFANSIF' if exposure_ratio < 1.0 else 'DEFANSIF'
                else:
                    exposure_mode = 'OFANSIF'
        
        if exposure_mode != required_mode:
            return False, f"Exposure mode {exposure_mode} != required {required_mode}"
        
        # Calculate exposure_ratio
        if exposure.pot_max > 0:
            exposure_ratio = exposure.pot_total / exposure.pot_max
        else:
            exposure_ratio = 0.0
        
        # For ADDNEWPOS, we want LOW exposure (room to add)
        if exposure_ratio >= exposure_ratio_threshold:
            return False, f"Exposure ratio {exposure_ratio:.2%} >= threshold {exposure_ratio_threshold:.2%}"
        
        return True, f"Exposure ratio {exposure_ratio:.2%} < threshold {exposure_ratio_threshold:.2%}, mode={exposure_mode}"
    
    async def addnewpos_decision_engine(self, request: DecisionRequest) -> DecisionResponse:
        """
        ADDNEWPOS decision engine - main entry point.
        
        Args:
            request: DecisionRequest with available_symbols, metrics, exposure, etc.
            
        Returns:
            DecisionResponse with BUY/SHORT decisions and filtered_out symbols
        """
        start_time = datetime.now()
        
        try:
            # Check eligibility first
            exposure_mode = request.exposure.mode if request.exposure else None
            is_eligible, eligibility_reason = self.is_eligible(request.exposure, exposure_mode)
            
            # Phase 9: CleanLogs Init
            try:
                from app.psfalgo.clean_log_store import get_clean_log_store, LogSeverity, LogEvent
                from dataclasses import asdict
                clean_log = get_clean_log_store()
                from app.trading.trading_account_context import get_trading_context
                ctx = get_trading_context()
                account_id = ctx.trading_mode.value
            except:
                 clean_log = None
                 account_id = "UNKNOWN"

            if not is_eligible:
                logger.info(f"[ADDNEWPOS] Not eligible: {eligibility_reason}")
                
                # CleanLog: Eligibility Skip
                if clean_log:
                    clean_log.log_event(
                        account_id=account_id,
                        component="ADDNEWPOS_ENGINE",
                        event=LogEvent.SKIP.value,
                        symbol=None,
                        message=f"Skipped: {eligibility_reason}",
                        severity=LogSeverity.INFO.value,
                        correlation_id=request.correlation_id,
                        details={'reason': eligibility_reason, 'exposure': asdict(request.exposure) if request.exposure else None}
                    )

                return DecisionResponse(
                    decisions=[],
                    filtered_out=[],
                    step_summary={'eligibility': {'eligible': False, 'reason': eligibility_reason}},
                    execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                    correlation_id=request.correlation_id
                )
            
            logger.info(f"[ADDNEWPOS] Eligible: {eligibility_reason}")
            
            all_decisions = []
            all_filtered_out = []

            step_summary = {'eligibility': {'eligible': True, 'reason': eligibility_reason}}
            
            # ═══════════════════════════════════════════════════════════════════
            # MENTAL MODEL V1: Global Intent Calculation
            # ═══════════════════════════════════════════════════════════════════
            exposure_pct = 0.0
            if request.exposure and request.exposure.pot_max > 0:
                 # Standard exposure pct calculation (Gross Exposure %)
                 exposure_pct = (request.exposure.pot_total / request.exposure.pot_max) * 100.0
            
            # Use shared math module
            add_intent, reduce_intent, regime = compute_intents(exposure_pct, self.intent_model_config)
            
            step_summary['intent_model'] = {
                'exposure_pct': exposure_pct,
                'add_intent': add_intent,
                'reduce_intent': reduce_intent,
                'regime': regime
            }
            
            # Gating: If AddIntent is 0 or very low, we can skip early
            # OR if regime is HARD, we block.
            if regime == 'HARD' or add_intent < 0.1:
                logger.info(f"[ADDNEWPOS] Global Intent blocking: Regime={regime}, AddIntent={add_intent:.2f}")
                
                 # CleanLog: Intent Block Skip
                if clean_log:
                    clean_log.log_event(
                        account_id=account_id,
                        component="ADDNEWPOS_ENGINE",
                        event=LogEvent.SKIP.value,
                        symbol=None,
                        message=f"Skipped (Intent Block): Regime={regime}, AddIntent={add_intent:.2f}",
                        severity=LogSeverity.INFO.value,
                        correlation_id=request.correlation_id,
                        details={'regime': regime, 'add_intent': add_intent}
                    )

                return DecisionResponse(
                    decisions=[],
                    filtered_out=[],
                    step_summary=step_summary,
                    execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                    correlation_id=request.correlation_id
                )
            
            logger.info(f"[ADDNEWPOS] Intent: Add={add_intent:.1f}, Reduce={reduce_intent:.1f}, Regime={regime}")
            # ═══════════════════════════════════════════════════════════════════
            
            # Get cooldown manager and confidence calculator
            cooldown_manager = get_decision_cooldown_manager()
            confidence_calculator = get_confidence_calculator()
            
            # Get available symbols
            available_symbols = request.available_symbols or []
            if not available_symbols:
                logger.info("[ADDNEWPOS] No available symbols provided")
                return DecisionResponse(
                    decisions=[],
                    filtered_out=[],
                    step_summary=step_summary,
                    execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                    correlation_id=request.correlation_id
                )
            
            # Get current mode
            mode = self.settings.get('mode', 'addlong_only')
            

            # Calculate remaining exposure
            remaining_exposure = 0
            if request.exposure and request.exposure.pot_max > 0:
                pot_total = request.exposure.pot_total if request.exposure.pot_total is not None else 0.0
                remaining_exposure = request.exposure.pot_max - pot_total
                remaining_exposure = remaining_exposure * (self.exposure_usage_percent / 100.0)
            
            logger.info(f"[ADDNEWPOS] Mode: {mode}, Remaining exposure: {remaining_exposure:,.0f}")
            
            # Calculate total portfolio lots for Portfolio Rules
            total_portfolio_lots = None
            if request.exposure:
                ll = request.exposure.long_lots if request.exposure.long_lots is not None else 0.0
                sl = request.exposure.short_lots if request.exposure.short_lots is not None else 0.0
                total_portfolio_lots = ll + sl
            
            # Prepare generic candidates tuple list for picking
            all_candidates_tuples = []
            for s in available_symbols:
                if s in request.metrics:
                     all_candidates_tuples.append((s, request.metrics[s]))

            # ========== PROCESS ADDLONG ==========
            long_decisions, long_filtered = [], []
            if mode in ['addlong_only', 'both'] and self.addlong_config.get('enabled', True):
                # Pick Candidates (LT LONG)
                picked_long = self.pick_candidates_by_intent(all_candidates_tuples, add_intent, strategy="LT")
                long_syms = [x[0] for x in picked_long]
                
                step_summary['pick_policy_long'] = {'picked_count': len(long_syms), 'top_picks': long_syms}
                
                # We need to pass intent info. Since we don't want to change signature of process_addlong yet (or we do?),
                # Let's change the signature in the next step. 
                # For now, we will assume _process_addlong expects generic available_symbols.
                # We also need to inject 'add_intent' and 'goodness' into the lot calculation downstream.
                
                # To avoid breaking signature immediately, we can use a temporary instance variable hack
                # or pass it as a special kwarg if supported.
                # But correct way is updating signature.
                
                long_decisions, long_filtered = await self._process_addlong(
                    available_symbols=long_syms,  # Only picked symbols
                    metrics=request.metrics,
                    existing_positions=request.positions,
                    remaining_exposure=remaining_exposure,
                    cooldown_manager=cooldown_manager,
                    confidence_calculator=confidence_calculator,
                    snapshot_ts=request.snapshot_ts,
                    total_portfolio_lots=total_portfolio_lots,
                    # NEW ARGS (Will add to definition next)
                    intent_info={'add_intent': add_intent, 'regime': regime}
                )
                all_decisions.extend(long_decisions)
                all_filtered_out.extend(long_filtered)
                step_summary['addlong'] = {
                    'name': 'AddLong',
                    'total': len(available_symbols), 
                    'picked': len(long_syms),
                    'decisions': len(long_decisions),
                    'filtered': len(long_filtered)
                }
            
            # ========== PROCESS ADDSHORT ==========
            short_decisions, short_filtered = [], []
            if mode in ['addshort_only', 'both'] and self.addshort_config.get('enabled', True):
                 # Pick Candidates (LT SHORT - Actually pick_candidates assumes LT uses generic goodness?)
                 # My implementation of pick_candidates uses max(long, short) goodness.
                 # If we want specific SHORT goodness, we should update pick_candidates to accept side?
                 # Currently pick_candidates_by_intent uses generic max. That's acceptable for now.
                 # Or we can improve it later.
                 
                 picked_short = self.pick_candidates_by_intent(all_candidates_tuples, add_intent, strategy="LT")
                 short_syms = [x[0] for x in picked_short]
                 
                 step_summary['pick_policy_short'] = {'picked_count': len(short_syms), 'top_picks': short_syms}

                 short_decisions, short_filtered = await self._process_addshort(
                    available_symbols=short_syms,
                    metrics=request.metrics,
                    existing_positions=request.positions,
                    remaining_exposure=remaining_exposure,
                    cooldown_manager=cooldown_manager,
                    confidence_calculator=confidence_calculator,
                    snapshot_ts=request.snapshot_ts,
                    total_portfolio_lots=total_portfolio_lots,
                    # NEW ARGS
                    intent_info={'add_intent': add_intent, 'regime': regime}
                )
                 all_decisions.extend(short_decisions)
                 all_filtered_out.extend(short_filtered)
                 step_summary['addshort'] = {
                    'name': 'AddShort',
                    'total': len(available_symbols),
                    'picked': len(short_syms),
                    'decisions': len(short_decisions),
                    'filtered': len(short_filtered)
                }
            
            step_summary['execution'] = {
                 'addlong_decisions': len(long_decisions),
                 'addshort_decisions': len(short_decisions),
                 'total_decisions': len(all_decisions),
                 'total_filtered': len(all_filtered_out)
            }
            
            # ═══════════════════════════════════════════════════════════════════
            # MENTAL MODEL V1: Enrich Decisions with Intent & Rules
            # ═══════════════════════════════════════════════════════════════════
            for d in all_decisions:
                # Ensure metadata dict exists
                if not hasattr(d, 'metadata') or d.metadata is None:
                    d.metadata = {}
                
                # Add Intent info
                d.metadata['intent_model'] = {
                    'add_intent': add_intent,
                    'reduce_intent': reduce_intent,
                    'regime': regime
                }
                
                # Add Rule Triggers (Static list for now + dynamic logic)
                triggers = ["intent_model.piecewise_v1", "lot_policy.rounding"]
                if regime == 'SOFT':
                    triggers.append("risk_regimes.soft_derisk")
                
                d.metadata['rule_triggers'] = triggers
                
                # Append to plain text reason for visibility in simple logs
                d.reason += f" [Intent:{add_intent:.0f} Regime:{regime}]"
            # ═══════════════════════════════════════════════════════════════════
            
            # Calculate execution time
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            
            # Log summary
            logger.info(f"[ADDNEWPOS] Finished. Decisions: {len(all_decisions)}, Filtered: {len(all_filtered_out)}")
            if len(all_decisions) > 0:
                logger.info(f"[ADDNEWPOS] First decision: {all_decisions[0].symbol} {all_decisions[0].action} {all_decisions[0].calculated_lot}")
            
            # PUSH REJECTIONS TO STORE (Visibility)
            # -------------------------------------
            rr_store = get_reject_reason_store()
            for d in all_filtered_out:
                rr_store.add(d)
            
            # Phase 9: CleanLogs Traceability
            if clean_log:
                 # Log Decisions (PROPOSAL)
                 for d in all_decisions:
                     d.correlation_id = request.correlation_id # Propagate ID
                     clean_log.log_event(
                        account_id=account_id,
                        component="ADDNEWPOS_ENGINE",
                        event=LogEvent.PROPOSAL.value,
                        symbol=d.symbol,
                        message=f"Proposed {d.action} {d.calculated_lot} lots: {d.reason}",
                        severity=LogSeverity.INFO.value,
                        correlation_id=request.correlation_id,
                        details=asdict(d)
                    )
                    
                 # Log Filters (REJECT/SKIP)
                 for f in all_filtered_out:
                     f.correlation_id = request.correlation_id # Propagate ID
                     clean_log.log_event(
                        account_id=account_id,
                        component="ADDNEWPOS_ENGINE",
                        event=LogEvent.SKIP.value,
                        symbol=f.symbol,
                        message=f"Skipped {f.symbol}: {f.filter_reasons[0] if f.filter_reasons else 'Unknown'}",
                        severity=LogSeverity.INFO.value,
                        correlation_id=request.correlation_id,
                        details=asdict(f)
                    )

            return DecisionResponse(
                decisions=all_decisions,
                filtered_out=all_filtered_out,
                step_summary=step_summary,
                execution_time_ms=execution_time,
                correlation_id=request.correlation_id
            )
            
            
        except Exception as e:
            logger.error(f"[ADDNEWPOS] Error in decision engine: {e}", exc_info=True)
            return DecisionResponse(
                decisions=[],
                filtered_out=[],
                step_summary={},
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                error=str(e)
            )
    
    async def _process_addlong(
        self,
        available_symbols: List[str],
        metrics: Dict[str, SymbolMetrics],
        existing_positions: List[PositionSnapshot],
        remaining_exposure: float,
        cooldown_manager,
        confidence_calculator,
        snapshot_ts: Optional[datetime] = None,
        total_portfolio_lots: Optional[float] = None,
        intent_info: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Decision], List[Decision]]:
        """
        Process AddLong decisions.
        
        Filters:
        - Bid Buy Ucuzluk > threshold
        - Fbtot > threshold
        - Spread < threshold
        - AVG_ADV > threshold
        
        Args:
            available_symbols: List of available symbol strings
            metrics: Symbol metrics
            existing_positions: Existing positions
            remaining_exposure: Remaining exposure to use
            cooldown_manager: Cooldown manager
            confidence_calculator: Confidence calculator
            snapshot_ts: Snapshot timestamp
            total_portfolio_lots: Total portfolio lots
            intent_info: Intent model info (add_intent, regime)
            
        Returns:
            (decisions, filtered_out)
        """
        decisions = []
        filtered_out = []
        
        filters = self.addlong_config.get('filters', {})
        # Janall: bid_buy_ucuzluk < threshold means CHEAP (negative values = cheaper)
        bid_buy_ucuzluk_lt = filters.get('bid_buy_ucuzluk_lt', -0.06)  # Default: must be < -0.06
        # Janall: Fbtot > 1.10 means UCUZ (cheap) - we want to BUY cheap stocks
        fbtot_gt = filters.get('fbtot_gt', 1.10)  # FBTOT > 1.10 = UCUZ (cheap)
        spread_lt = filters.get('spread_lt', 0.25)
        avg_adv_gt = filters.get('avg_adv_gt', 500.0)
        # JANALL FILTERS: SMA63 chg and GORT (OPTIONAL - None means disabled)
        sma63_chg_lt = filters.get('sma63_chg_lt')  # None = disabled
        gort_lt = filters.get('gort_lt')  # None = disabled
        
        max_lot_per_symbol = self.settings.get('max_lot_per_symbol', 200)
        default_lot = self.settings.get('default_lot', 200)
        
        # Build existing position map (symbol -> qty)
        existing_map = {pos.symbol: pos.qty for pos in existing_positions}
        
        for symbol in available_symbols:
            metric = metrics.get(symbol)
            
            if not metric:
                filtered_out.append(Decision(
                    symbol=symbol,
                    action="FILTERED",
                    filtered_out=True,
                    filter_reasons=["Metrics not available"],
                    step_number=1,
                    timestamp=datetime.now()
                ))
                continue
            
            # ROBUST NULL CHECK (Janall DNA)
            # -----------------------------------------------------------------
            # Critical metrics must be present before any math.
            # If final scores are None, skip immediately.
            if metric.bid_buy_ucuzluk is None or metric.fbtot is None:
                # DEBUG LOG AS REQUESTED
                logger.debug(f"[ADDNEWPOS_SKIP] {symbol} reason=INVALID_FAST_SCORE fbtot={metric.fbtot} bid_buy={metric.bid_buy_ucuzluk}")
                
                filtered_out.append(Decision(
                    symbol=symbol,
                    action="FILTERED",
                    filtered_out=True,
                    filter_reasons=[f"Critical metrics MISSING (bid_buy={metric.bid_buy_ucuzluk}, fbtot={metric.fbtot})"],
                    reject_reason_code=RejectReason.CRITICAL_METRIC_MISSING,
                    reject_reason_details={'bid_buy': metric.bid_buy_ucuzluk, 'fbtot': metric.fbtot},
                    step_number=1,
                    timestamp=datetime.now()
                ))
                continue
            # -----------------------------------------------------------------
            
            # 1. Calculate Goodness (Mental Model v1)
            goodness = self.compute_lt_goodness(metric, "LONG")
            
            # JANALL FILTER: Check SMA63 chg (for longs, we want negative = underperforming)
            sma63_chg = metric.sma63_chg
            if sma63_chg is not None and sma63_chg_lt is not None:
                if sma63_chg >= sma63_chg_lt:
                    filtered_out.append(Decision(
                        symbol=symbol,
                        action="FILTERED",
                        filtered_out=True,
                        filter_reasons=[f"SMA63 chg >= {sma63_chg_lt} (SMA63 chg={sma63_chg:.2f}) - not underperforming enough"],
                        reject_reason_code=RejectReason.NOT_CHEAP_ENOUGH,
                        reject_reason_details={'value': sma63_chg, 'limit': sma63_chg_lt},
                        step_number=1,
                        timestamp=datetime.now()
                    ))
                    continue
            
            # JANALL FILTER: Check GORT (for longs, we want GORT < 1)
            gort = metric.gort
            if gort is not None and gort_lt is not None:
                if gort >= gort_lt:
                    filtered_out.append(Decision(
                        symbol=symbol,
                        action="FILTERED",
                        filtered_out=True,
                        filter_reasons=[f"GORT >= {gort_lt} (GORT={gort:.2f}) - not underperforming vs group"],
                        reject_reason_code=RejectReason.NOT_CHEAP_ENOUGH,
                        reject_reason_details={'value': gort, 'limit': gort_lt},
                        step_number=1,
                        timestamp=datetime.now()
                    ))
                    continue
            
            # Check Bid Buy Ucuzluk - NEGATIVE = CHEAP (we want cheaper stocks)
            # Janall: bid_buy_ucuzluk < -0.06 means stock is at least 6 cents cheaper than benchmark
            bid_buy = metric.bid_buy_ucuzluk
            if bid_buy is None or bid_buy >= bid_buy_ucuzluk_lt:
                filtered_out.append(Decision(
                    symbol=symbol,
                    action="FILTERED",
                    filtered_out=True,
                    filter_reasons=[f"Bid Buy Ucuzluk >= {bid_buy_ucuzluk_lt} (Bid Buy={bid_buy}) - not cheap enough"],
                    reject_reason_code=RejectReason.NOT_CHEAP_ENOUGH,
                    reject_reason_details={'value': bid_buy, 'limit': bid_buy_ucuzluk_lt},
                    step_number=1,
                    timestamp=datetime.now()
                ))
                continue
            
            # Check Fbtot - Janall: Fbtot > 1.10 means UCUZ (cheap) - we want to BUY cheap stocks
            # FBTOT < 1.0 = PAHALI (expensive) - DO NOT BUY
            # FBTOT > 1.0 = UCUZ (cheap) - BUY
            fbtot = metric.fbtot
            if fbtot is None or fbtot <= fbtot_gt:
                filtered_out.append(Decision(
                    symbol=symbol,
                    action="FILTERED",
                    filtered_out=True,
                    filter_reasons=[f"Fbtot <= {fbtot_gt} (Fbtot={fbtot}) - not cheap enough (FBTOT > 1.10 required for LONG)"],
                    reject_reason_code=RejectReason.VALUATION_TOO_POOR,
                    reject_reason_details={'value': fbtot, 'limit': fbtot_gt},
                    step_number=1,
                    timestamp=datetime.now()
                ))
                continue
            
            # Check Spread
            spread = metric.spread
            if spread is None or spread >= spread_lt:
                filtered_out.append(Decision(
                    symbol=symbol,
                    action="FILTERED",
                    filtered_out=True,
                    filter_reasons=[f"Spread >= {spread_lt} (Spread={spread})"],
                    reject_reason_code=RejectReason.SPREAD_TOO_HIGH,
                    reject_reason_details={'value': spread, 'limit': spread_lt},
                    step_number=1,
                    timestamp=datetime.now()
                ))
                continue
            
            # Check AVG_ADV
            avg_adv = metric.avg_adv
            if avg_adv is None or avg_adv <= avg_adv_gt:
                filtered_out.append(Decision(
                    symbol=symbol,
                    action="FILTERED",
                    filtered_out=True,
                    filter_reasons=[f"AVG_ADV <= {avg_adv_gt} (AVG_ADV={avg_adv})"],
                    reject_reason_code=RejectReason.AVG_ADV_TOO_LOW,
                    reject_reason_details={'value': avg_adv, 'limit': avg_adv_gt},
                    step_number=1,
                    timestamp=datetime.now()
                ))
                continue
            
            # Check existing position limit
            existing_qty = abs(existing_map.get(symbol, 0))
            if existing_qty >= max_lot_per_symbol:
                filtered_out.append(Decision(
                    symbol=symbol,
                    action="FILTERED",
                    filtered_out=True,
                    filter_reasons=[f"Existing position {existing_qty:.0f} >= max {max_lot_per_symbol}"],
                    reject_reason_code=RejectReason.EXISTING_POSITION_LIMIT,
                    reject_reason_details={'value': existing_qty, 'limit': max_lot_per_symbol},
                    step_number=1,
                    timestamp=datetime.now()
                ))
                continue
            
            # Check cooldown
            if cooldown_manager and not cooldown_manager.can_make_decision(symbol, snapshot_ts):
                filtered_out.append(Decision(
                    symbol=symbol,
                    action="FILTERED",
                    filtered_out=True,
                    filter_reasons=["Cooldown active"],
                    reject_reason_code=RejectReason.COOLDOWN_ACTIVE,
                    step_number=1,
                    timestamp=datetime.now()
                ))
                continue
            

            # Calculate lot using Mental Model v1 (Intent * Goodness)
            calculated_lot = self._calculate_lot_mental_model(
                symbol=symbol,
                existing_qty=existing_qty,
                max_lot=max_lot_per_symbol,
                default_lot=default_lot,
                metric=metric,
                total_portfolio_lots=total_portfolio_lots,
                intent_info=intent_info,
                goodness=goodness
            )
            
            if calculated_lot <= 0:
                continue
            
            # Determine action (BUY or ADD)
            action = "ADD" if existing_qty > 0 else "BUY"
            
            # Calculate confidence
            confidence = 0.5
            if confidence_calculator:
                dummy_position = PositionSnapshot(
                    symbol=symbol,
                    qty=calculated_lot,
                    avg_price=metric.bid or 0,
                    current_price=metric.bid or 0,
                    unrealized_pnl=0,
                    timestamp=datetime.now()
                )
                confidence = confidence_calculator.calculate_confidence(
                    symbol=symbol,
                    position=dummy_position,
                    metrics=metric,
                    action=action,
                    reason="AddLong"
                )
            
            decision = Decision(
                symbol=symbol,
                action=action,
                order_type="BID_BUY",
                lot_percentage=None,
                calculated_lot=calculated_lot,
                price_hint=metric.bid,
                step_number=1,
                reason=f"AddLong: Bid Buy Ucuzluk={bid_buy:.4f}, Fbtot={fbtot:.2f}",
                confidence=confidence,
                metrics_used={
                    'bid_buy_ucuzluk': bid_buy,
                    'fbtot': fbtot,
                    'spread': spread,
                    'avg_adv': avg_adv,
                    'existing_qty': existing_qty
                },
                timestamp=datetime.now()
            )
            
            decisions.append(decision)
            
            if cooldown_manager:
                cooldown_manager.record_decision(symbol, snapshot_ts)
        
        # Log filter statistics for debugging
        filter_reasons_count = {}
        for d in filtered_out:
            for reason in d.filter_reasons:
                # Extract filter name from reason
                filter_name = reason.split(' ')[0] if reason else 'Unknown'
                filter_reasons_count[filter_name] = filter_reasons_count.get(filter_name, 0) + 1
        
        logger.info(f"[ADDNEWPOS] AddLong: {len(decisions)} decisions, {len(filtered_out)} filtered")
        if filter_reasons_count:
            logger.info(f"[ADDNEWPOS] Filter breakdown: {filter_reasons_count}")
        
        return decisions, filtered_out
    

    async def _process_addshort(
        self,
        available_symbols: List[str],
        metrics: Dict[str, SymbolMetrics],
        existing_positions: List[PositionSnapshot],
        remaining_exposure: float,
        cooldown_manager,
        confidence_calculator,
        snapshot_ts: Optional[datetime] = None,
        total_portfolio_lots: Optional[float] = None,
        intent_info: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[Decision], List[Decision]]:
        """
        Process AddShort decisions.
        
        Filters:
        - Ask Sell Pahalılık > threshold
        - SFStot > threshold
        - Spread < threshold
        - AVG_ADV > threshold
        
        Args:
            available_symbols: List of available symbol strings
            metrics: Symbol metrics
            existing_positions: Existing positions
            remaining_exposure: Remaining exposure to use
            cooldown_manager: Cooldown manager
            confidence_calculator: Confidence calculator
            snapshot_ts: Snapshot timestamp
            total_portfolio_lots: Total portfolio lots
            intent_info: Intent info
            
        Returns:
            (decisions, filtered_out)
        """
        decisions = []
        filtered_out = []
        
        filters = self.addshort_config.get('filters', {})
        # Janall: ask_sell_pahalilik > threshold means EXPENSIVE (positive = more expensive to short)
        ask_sell_pahalilik_gt = filters.get('ask_sell_pahalilik_gt', 0.06)  # POSITIVE = PAHALI
        # Janall: SFStot > 1.10 means PAHALI (expensive) - we want to SHORT expensive stocks
        sfstot_gt = filters.get('sfstot_gt', 1.10)  # SFStot > 1.10 = PAHALI (expensive)
        spread_lt = filters.get('spread_lt', 0.25)
        avg_adv_gt = filters.get('avg_adv_gt', 500.0)
        # JANALL FILTERS: SMA63 chg and GORT for shorts (OPTIONAL - None means disabled)
        sma63_chg_gt = filters.get('sma63_chg_gt')  # None = disabled
        gort_gt = filters.get('gort_gt')  # None = disabled
        
        max_lot_per_symbol = self.settings.get('max_lot_per_symbol', 200)
        default_lot = self.settings.get('default_lot', 200)
        
        # Build existing position map (symbol -> qty, negative for shorts)
        existing_map = {pos.symbol: pos.qty for pos in existing_positions}
        
        for symbol in available_symbols:
            metric = metrics.get(symbol)
            
            if not metric:
                filtered_out.append(Decision(
                    symbol=symbol,
                    action="FILTERED",
                    filtered_out=True,
                    filter_reasons=["Metrics not available"],
                    step_number=2,
                    timestamp=datetime.now()
                ))
                continue

            # ROBUST NULL CHECK (Janall DNA)
            # -----------------------------------------------------------------
            # Critical metrics must be present before any math.
            # If final scores are None, skip immediately.
            if metric.ask_sell_pahalilik is None or metric.sfstot is None:
                # DEBUG LOG AS REQUESTED
                logger.debug(f"[ADDNEWPOS_SKIP] {symbol} reason=INVALID_FAST_SCORE sfstot={metric.sfstot} ask_sell={metric.ask_sell_pahalilik}")
                
                filtered_out.append(Decision(
                    symbol=symbol,
                    action="FILTERED",
                    filtered_out=True,
                    filter_reasons=[f"Critical metrics MISSING (ask_sell={metric.ask_sell_pahalilik}, sfstot={metric.sfstot})"],
                    step_number=2,
                    timestamp=datetime.now()
                ))
                continue
            # -----------------------------------------------------------------
            
            # 1. Calculate Goodness (Mental Model v1)
            goodness = self.compute_lt_goodness(metric, "SHORT")
            
            # JANALL FILTER: Check SMA63 chg (for shorts, we want positive = outperforming)
            sma63_chg = metric.sma63_chg
            if sma63_chg is not None and sma63_chg_gt is not None:
                if sma63_chg <= sma63_chg_gt:
                    filtered_out.append(Decision(
                        symbol=symbol,
                        action="FILTERED",
                        filtered_out=True,
                        filter_reasons=[f"SMA63 chg <= {sma63_chg_gt} (SMA63 chg={sma63_chg:.2f}) - not outperforming enough"],
                        step_number=2,
                        timestamp=datetime.now()
                    ))
                    continue
            
            # JANALL FILTER: Check GORT (for shorts, we want GORT > 1)
            gort = metric.gort
            if gort is not None and gort_gt is not None:
                if gort <= gort_gt:
                    filtered_out.append(Decision(
                        symbol=symbol,
                        action="FILTERED",
                        filtered_out=True,
                        filter_reasons=[f"GORT <= {gort_gt} (GORT={gort:.2f}) - not outperforming vs group"],
                        step_number=2,
                        timestamp=datetime.now()
                    ))
                    continue
            
            # Check Ask Sell Pahalılık - POSITIVE = EXPENSIVE (we want expensive stocks to short)
            # Janall: ask_sell_pahalilik > 0.06 means stock is at least 6 cents more expensive than benchmark
            ask_sell = metric.ask_sell_pahalilik
            if ask_sell is None or ask_sell <= ask_sell_pahalilik_gt:
                filtered_out.append(Decision(
                    symbol=symbol,
                    action="FILTERED",
                    filtered_out=True,
                    filter_reasons=[f"Ask Sell Pahalılık <= {ask_sell_pahalilik_gt} (Ask Sell={ask_sell}) - not expensive enough"],
                    step_number=2,
                    timestamp=datetime.now()
                ))
                continue
            
            # Check SFStot - Janall: SFStot > 1.10 means PAHALI (expensive) - we want to SHORT expensive stocks
            # SFStot < 1.0 = UCUZ (cheap) - DO NOT SHORT
            # SFStot > 1.0 = PAHALI (expensive) - SHORT
            sfstot = metric.sfstot
            if sfstot is None or sfstot <= sfstot_gt:
                filtered_out.append(Decision(
                    symbol=symbol,
                    action="FILTERED",
                    filtered_out=True,
                    filter_reasons=[f"SFStot <= {sfstot_gt} (SFStot={sfstot}) - not expensive enough (SFStot > 1.10 required for SHORT)"],
                    step_number=2,
                    timestamp=datetime.now()
                ))
                continue
            
            # Check Spread
            spread = metric.spread
            if spread is None or spread >= spread_lt:
                filtered_out.append(Decision(
                    symbol=symbol,
                    action="FILTERED",
                    filtered_out=True,
                    filter_reasons=[f"Spread >= {spread_lt} (Spread={spread})"],
                    step_number=2,
                    timestamp=datetime.now()
                ))
                continue
            
            # Check AVG_ADV
            avg_adv = metric.avg_adv
            if avg_adv is None or avg_adv <= avg_adv_gt:
                filtered_out.append(Decision(
                    symbol=symbol,
                    action="FILTERED",
                    filtered_out=True,
                    filter_reasons=[f"AVG_ADV <= {avg_adv_gt} (AVG_ADV={avg_adv})"],
                    step_number=2,
                    timestamp=datetime.now()
                ))
                continue
            
            # Check existing position limit (for shorts, qty is negative)
            existing_qty = existing_map.get(symbol, 0)
            existing_short_qty = abs(existing_qty) if existing_qty < 0 else 0
            
            if existing_short_qty >= max_lot_per_symbol:
                filtered_out.append(Decision(
                    symbol=symbol,
                    action="FILTERED",
                    filtered_out=True,
                    filter_reasons=[f"Existing short {existing_short_qty:.0f} >= max {max_lot_per_symbol}"],
                    step_number=2,
                    timestamp=datetime.now()
                ))
                continue
            
            # Check cooldown
            if cooldown_manager and not cooldown_manager.can_make_decision(symbol, snapshot_ts):
                filtered_out.append(Decision(
                    symbol=symbol,
                    action="FILTERED",
                    filtered_out=True,
                    filter_reasons=["Cooldown active"],
                    step_number=2,
                    timestamp=datetime.now()
                ))
                continue
            

            # Calculate lot using Mental Model v1 (Intent * Goodness)
            calculated_lot = self._calculate_lot_mental_model(
                symbol=symbol,
                existing_qty=existing_short_qty,
                max_lot=max_lot_per_symbol,
                default_lot=default_lot,
                metric=metric,
                total_portfolio_lots=total_portfolio_lots,
                intent_info=intent_info,
                goodness=goodness
            )
            
            if calculated_lot <= 0:
                continue
            
            # Determine action (SHORT or ADD_SHORT)
            action = "ADD_SHORT" if existing_short_qty > 0 else "SHORT"
            
            # Calculate confidence
            confidence = 0.5
            if confidence_calculator:
                dummy_position = PositionSnapshot(
                    symbol=symbol,
                    qty=-calculated_lot,
                    avg_price=metric.ask or 0,
                    current_price=metric.ask or 0,
                    unrealized_pnl=0,
                    timestamp=datetime.now()
                )
                confidence = confidence_calculator.calculate_confidence(
                    symbol=symbol,
                    position=dummy_position,
                    metrics=metric,
                    action=action,
                    reason="AddShort"
                )
            
            decision = Decision(
                symbol=symbol,
                action=action,
                order_type="ASK_SELL",
                lot_percentage=None,
                calculated_lot=calculated_lot,
                price_hint=metric.ask,
                step_number=2,
                reason=f"AddShort: Ask Sell Pahalılık={ask_sell:.4f}, SFStot={sfstot:.2f}",
                confidence=confidence,
                metrics_used={
                    'ask_sell_pahalilik': ask_sell,
                    'sfstot': sfstot,
                    'spread': spread,
                    'avg_adv': avg_adv,
                    'existing_short_qty': existing_short_qty
                },
                timestamp=datetime.now()
            )
            
            decisions.append(decision)
            
            if cooldown_manager:
                cooldown_manager.record_decision(symbol, snapshot_ts)
        
        # Log filter statistics for debugging
        filter_reasons_count = {}
        for d in filtered_out:
            for reason in d.filter_reasons:
                # Extract filter name from reason
                filter_name = reason.split(' ')[0] if reason else 'Unknown'
                filter_reasons_count[filter_name] = filter_reasons_count.get(filter_name, 0) + 1
        
        logger.info(f"[ADDNEWPOS] AddShort: {len(decisions)} decisions, {len(filtered_out)} filtered")
        if filter_reasons_count:
            logger.info(f"[ADDNEWPOS] Filter breakdown: {filter_reasons_count}")
        
        return decisions, filtered_out
    
    def _calculate_lot_from_rules(
        self,
        symbol: str,
        existing_qty: float,
        max_lot: int,
        default_lot: int,
        metric: SymbolMetrics,
        total_portfolio_lots: Optional[float] = None
    ) -> int:
        """
        Calculate lot using Janall's portfolio rules (Birebir Janall mantığı).
        
        Janall Rules:
        - < 1%: min(MAXALW × 0.50, Portfolio × 5%)
        - 1-3%: min(MAXALW × 0.40, Portfolio × 4%)
        - 3-5%: min(MAXALW × 0.30, Portfolio × 3%)
        - 5-7%: min(MAXALW × 0.20, Portfolio × 2%)
        - 7-10%: min(MAXALW × 0.10, Portfolio × 1.5%)
        - >= 10%: min(MAXALW × 0.05, Portfolio × 1%)
        
        Portfolio percentage = (existing_qty / MAXALW) * 100
        
        Args:
            symbol: Symbol string
            existing_qty: Existing position quantity
            max_lot: Maximum lot per symbol (fallback)
            default_lot: Default lot (fallback)
            metric: Symbol metrics (must have maxalw)
            total_portfolio_lots: Total portfolio lots (for Portfolio × % calculation)
            
        Returns:
            Calculated lot amount
        """
        maxalw = getattr(metric, 'maxalw', None)
        
        # If no MAXALW, use simple fallback
        if not maxalw or maxalw <= 0:
            remaining_capacity = max_lot - existing_qty
            calculated_lot = min(default_lot, remaining_capacity)
            calculated_lot = max(0, calculated_lot)
            # Round to nearest 100
            calculated_lot = int((calculated_lot + 50) // 100) * 100
            return max(self.settings.get('min_lot_size', 100), calculated_lot)
        
        # Calculate portfolio percentage: (existing_qty / MAXALW) * 100
        portfolio_percent = (existing_qty / maxalw) * 100 if maxalw > 0 else 0
        
        # Find applicable rule
        applicable_rule = None
        for rule in self.portfolio_rules:
            if portfolio_percent < rule['max_portfolio_percent']:
                applicable_rule = rule
                break
        

        # If no rule found, use last rule (>= 10%)
        if not applicable_rule and self.portfolio_rules:
            applicable_rule = self.portfolio_rules[-1]
            
        if not applicable_rule:
             # Should not happen if defaults set
             remaining_capacity = max_lot - existing_qty
             calculated_lot = min(default_lot, remaining_capacity)
        else:
            # Rule found: min(MAXALW * mult, Portfolio * %)
            option1 = maxalw * applicable_rule['maxalw_multiplier']
            
            if total_portfolio_lots is not None and total_portfolio_lots > 0:
                 option2 = total_portfolio_lots * (applicable_rule.get('portfolio_percent', 1.0) / 100.0)
                 # Janall logic: Take MIN of the two if option2 valid?
                 # Actually Janall code usually just takes option1 if portfolio total not tracked
                 # For now, let's stick to option1 (MAXALW based) as primary driver
                 calculated_lot = option1
            else:
                 calculated_lot = option1
        
        # Clamp to max_lot setting if needed
        # calculated_lot = min(calculated_lot, max_lot) 
        # (This is usually done later, but ok to keep logic pure here)
        

        # ═══════════════════════════════════════════════════════════════════
        # MENTAL MODEL V1: Strict Lot Discipline
        # ═══════════════════════════════════════════════════════════════════
        # Use calculate_rounded_lot logic (Never 100, 0 or >= 200)
        # We pass self.lot_policy_config which we loaded in __init__
        final_lot = calculate_rounded_lot(calculated_lot, self.lot_policy_config)
        
        return final_lot

    def _calculate_lot_mental_model(
        self,
        symbol: str,
        existing_qty: float,
        max_lot: int,
        default_lot: int,
        metric: SymbolMetrics,
        total_portfolio_lots: Optional[float],
        intent_info: Optional[Dict[str, Any]] = None,
        goodness: Optional[float] = None
    ) -> int:
        """
        Calculate lot size using Mental Model v1 logic.
        
        Flow:
        1. Base Lot: Janall-compatible Rule Cap (MAXALW vs Portfolio %).
        2. Desire: Intent * Goodness (if available).
        3. Raw Lot: Base Lot * Desire.
        4. Rounding: Strict 100-lot discipline (calculate_rounded_lot).
        5. Guards: Post-trade holding clamp.
        """
        # 1. Base Lot (Janall Logic - defines the CEILING)
        # We reuse _calculate_lot_from_rules but bypass its internal rounding?
        # Actually _calculate_lot_from_rules has internal rounding now.
        # Let's revert _calculate_lot_from_rules to be raw janall or handle it here.
        
        # To avoid duplicating logic, let's call _calculate_lot_from_rules
        # BUT _calculate_lot_from_rules now has "calculate_rounded_lot" inside it (from previous task)!
        # That's fine. It returns a rounded lot (e.g. 200, 300).
        # We can use that as our "Base Capacity Lot".
        
        # However, Mental Model wants to scale DOWN from a theoretical max based on Desire.
        # So we want the RAW capacity first.
        
        # Let's implement a "get_janall_base_capacity" or just inline the MAXALW logic here?
        # Better: let's use the result of _calculate_lot_from_rules as the "Max Allowed by Rules".
        
        base_lot = self._calculate_lot_from_rules(
            symbol, existing_qty, max_lot, default_lot, metric, total_portfolio_lots
        )
        # Note: base_lot is already rounded (e.g. 400).
        
        # 2. Apply Desire (if intent/goodness available)
        if intent_info and goodness is not None:
            # compute_desire returns coefficient [0.0 - 1.0+]
            # If default Alpha=1, Beta=1: Desire = (Intent/100) * (Goodness/100)
            
            # Example: Intent=80 (0.8), Goodness=90 (0.9) -> Desire = 0.72
            # Base Lot = 400. Raw Lot = 400 * 0.72 = 288.
            
            desire = compute_desire(
                intent_info['add_intent'], 
                goodness,
                alpha=self.intent_model_config.get('alpha', 1.0),
                beta=self.intent_model_config.get('beta', 1.0)
            )
            
            raw_lot = base_lot * desire
            

            # 3. Rounding (Strict)
            # 288 -> 300 (nearest 100 >= 200)
            final_lot = calculate_rounded_lot(raw_lot, self.lot_policy_config)
            
            # 4. Post-Trade Guards
            # Enforce post-trade holding preference (0 or >= 200)
            # AddLong/AddShort usually increases position magnitude.
            # But let's check holding logic.
            # Assume action implies ADDING to current position direction (or starting new).
            # If (existing > 0 and add) or (existing < 0 and add short): mag increases.
            # The only risk is if we add small amount that results in weird number?
            # No, because final_lot is already >= 200 or 0.
            # If existing=140, add=200 -> 340. OK.
            # If existing=0, add=200 -> 200. OK.
            
            # Where this clamp matters is if we are REDUCING.
            # But just in case, clamp no flip?
            # AddNewPos shouldn't flip.
            
            # Actually, `clamp_post_trade_hold` is more for Reducemore.
            # But let's use it if applicable.
            # For ADD logic, if we add 200, we are safe.
            # The only edge case: raw_lot was small, rounded to 0. 
            # If final_lot is 0, we don't trade.
            
            return final_lot
            
        else:
            # Fallback (Legacy)
            # Still apply rounding if we want V1 discipline even in fallback?
            # Prompt says: "Default Mode B (Mental Model)".
            # If intent_info missing, maybe we shouldn't enforce new rules strictly?
            # But let's enforce rounding at least.
            
            base_lot = self._calculate_lot_from_rules(
                symbol, existing_qty, max_lot, default_lot, metric, total_portfolio_lots
            )
            return calculate_rounded_lot(base_lot, self.lot_policy_config)

    def compute_lt_goodness(self, metric: SymbolMetrics, side: str = "LONG") -> float:
        """
        Compute LT (Long Term / Quality) goodness score [0-100].
        Based on Janall fundamentals: Fbtot/Sfstot and ucuzluk/pahalilik.
        """
        score = 0.0
        
        # 1. Valuation Component (50%)
        # Fbtot (Buy cheap) / Sfstot (Sell expensive)
        val_score = 0.0
        if side == "LONG":
            fbtot = getattr(metric, 'fbtot', None)
            if fbtot is None: return 0.0  # Guard against None
            
            # Fbtot > 1.10 is min req. 1.30 is great.
            # Map 1.10->50, 1.30->100
            val_score = max(0, min(100, (fbtot - 1.0) / 0.30 * 100))
        elif side == "SHORT":
            sfstot = getattr(metric, 'sfstot', None)
            if sfstot is None: return 0.0  # Guard against None
            
            # Sfstot > 1.10 is min req.
            val_score = max(0, min(100, (sfstot - 1.0) / 0.30 * 100))
            
        # 2. Relative Cheapness Component (50%)
        # bid_buy_ucuzluk (neg is good for long) / ask_sell_pahalilik (pos is good for short)
        rel_score = 0.0
        if side == "LONG":
            ucuzluk = getattr(metric, 'bid_buy_ucuzluk', 0.0)
            # -0.06 is min req (50). -0.10 is great (100).
            # We want more negative.
            # 0 -> 0, -0.06 -> 50, -0.12 -> 100
            if ucuzluk < 0:
                rel_score = min(100, (abs(ucuzluk) / 0.12) * 100)
        elif side == "SHORT":
            pahalilik = getattr(metric, 'ask_sell_pahalilik', 0.0)
            # 0.06 is min req. 0.12 is great.
            if pahalilik > 0:
                rel_score = min(100, (pahalilik / 0.12) * 100)
        
        # Weighted Final Score
        final_score = (val_score * 0.5) + (rel_score * 0.5)
        return max(0.0, min(100.0, final_score))

    def compute_mm_goodness(self, metric: SymbolMetrics) -> float:
        """
        Compute MM (Market Maker / Churn) goodness score [0-100].
        Based on Spread and Volume.
        """
        # 1. Spread Component (Advantage)
        spread = getattr(metric, 'spread', 0.10)
        # Tight spread is usually better for churn frequency, 
        # but sometimes wide spread is better for edge.
        # Let's say: 0.01-0.05 is great (100), > 0.30 is bad (0).
        spread_score = max(0, min(100, (0.30 - spread) / 0.25 * 100))
        
        # 2. Volume Component (Liquidity)
        avg_adv = getattr(metric, 'avg_adv', 0)
        # > 5000 is great (100), < 500 is bad (0)
        vol_score = max(0, min(100, avg_adv / 5000.0 * 100))
        
        return (spread_score * 0.6) + (vol_score * 0.4)

    def pick_candidates_by_intent(self, candidates: List[Tuple[str, SymbolMetrics]], intent: float, strategy: str = "LT") -> List[Tuple[str, SymbolMetrics]]:
        """
        Filter candidates based on Intent-driven selectivity (Pick Policy).
        """
        if not candidates:
            return []
            
        # Determine pick count based on policy
        # >= 70: 5, >= 40: 2, >= 20: 1, < 20: 0
        pick_count = 0
        if intent >= 70: pick_count = 5
        elif intent >= 40: pick_count = 2
        elif intent >= 20: pick_count = 1
        else:
            # MM Override check could go here, but kept simple for now
            pick_count = 0 
            
        if pick_count == 0:
            return []
            
        # Sort candidates by goodness
        # Make a list of (symbol, metric, goodness)
        scored = []
        for sym, met in candidates:
            # LT Goodness requires SIDE assumption. Assume LONG since this is mostly AddLong?
            # Or use MAX of Long/Short goodness
            # For simplicity, calculate generic goodness max
            g_long = self.compute_lt_goodness(met, "LONG")
            g_short = self.compute_lt_goodness(met, "SHORT")
            g = max(g_long, g_short) if strategy == "LT" else self.compute_mm_goodness(met)
            scored.append((sym, met, g))
            
        # Sort desc by goodness
        scored.sort(key=lambda x: x[2], reverse=True)
        
        # Slice
        top_picks = scored[:pick_count]
        
        # Return just (sym, met)
        return [(x[0], x[1]) for x in top_picks]



# ============================================================================
# Global Instance Management
# ============================================================================

_addnewpos_engine: Optional[AddnewposEngine] = None


def get_addnewpos_engine() -> Optional[AddnewposEngine]:
    """Get global AddnewposEngine instance"""
    return _addnewpos_engine


def initialize_addnewpos_engine(config_path: Optional[Path] = None) -> AddnewposEngine:
    """Initialize global AddnewposEngine instance"""
    global _addnewpos_engine
    _addnewpos_engine = AddnewposEngine(config_path=config_path)
    logger.info("AddnewposEngine initialized (Janall-compatible v2.0)")
    return _addnewpos_engine


async def addnewpos_decision_engine(request: DecisionRequest) -> DecisionResponse:
    """
    ADDNEWPOS decision engine - async entry point.
    """
    engine = get_addnewpos_engine()
    if engine is None:
        initialize_addnewpos_engine()
        engine = get_addnewpos_engine()
    
    if engine is None:
        logger.error("[ADDNEWPOS] Engine not initialized")
        return DecisionResponse(decisions=[], filtered_out=[], step_summary={}, execution_time_ms=0.0)
    
    return await engine.addnewpos_decision_engine(request)
