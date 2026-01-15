"""
Decision Engine

Consumes events from streams, maintains state, applies risk rules, produces Intents.
"""

import time
import signal
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from app.core.logger import logger
from app.core.redis_client import get_redis_client
from app.event_driven.state.event_log import EventLog
from app.event_driven.state.store import StateStore
from app.event_driven.contracts.events import (
    ExposureEvent,
    SessionEvent,
    IntentEvent,
    BaseEvent,
    OrderClassification,
)
from app.event_driven.decision_engine.policy_table import PolicyDecisionTable, PolicyMode
from app.event_driven.decision_engine.lt_band_controller import LTBandController
from app.event_driven.decision_engine.intent_arbiter import IntentArbiter
from app.event_driven.reporting.regime_transition_logger import RegimeTransitionLogger
from app.event_driven.reporting.cap_recovery_tracker import CapRecoveryTracker
from app.event_driven.decision_engine.hard_exit_engine import HardExitEngine
from app.event_driven.decision_engine.lt_trim_engine import LTTrimEngine


class DecisionEngine:
    """Decision Engine - the Brain of the system"""
    
    def __init__(self, worker_name: str = "decision_engine"):
        self.worker_name = worker_name
        self.running = False
        self.event_log: Optional[EventLog] = None
        self.state_store: Optional[StateStore] = None
        self.risk_rules: Dict[str, Any] = {}
        
        # State
        self.latest_exposure: Optional[Dict[str, Any]] = None
        self.latest_session: Optional[Dict[str, Any]] = None
        self.current_mode: PolicyMode = PolicyMode.NORMAL
        
        # Policy decision table
        self.policy_table: Optional[PolicyDecisionTable] = None
        
        # LT Band Controller
        self.lt_band_controller: Optional[LTBandController] = None
        
        # Intent Arbiter
        self.intent_arbiter: Optional[IntentArbiter] = None
        
        # Reporting trackers
        self.regime_logger: Optional[RegimeTransitionLogger] = None
        self.cap_recovery_tracker: Optional[CapRecoveryTracker] = None
        
        # Hard Exit Engine
        self.hard_exit_engine: Optional[HardExitEngine] = None
        
        # LT Trim Engine
        self.lt_trim_engine: Optional[LTTrimEngine] = None

        
        # Pending intents (collected before arbitration)
        self.pending_intents: List[Dict[str, Any]] = []
        
        # Consumer group name
        self.consumer_group = "decision_engine"
        self.consumer_name = f"{worker_name}_{int(time.time())}"
    
    def connect(self):
        """Connect to Redis and initialize consumer groups"""
        try:
            redis_client = get_redis_client().sync
            if not redis_client:
                raise RuntimeError("Redis client not available")
            
            self.event_log = EventLog(redis_client=redis_client)
            self.state_store = StateStore(redis_client=redis_client)
            
            # Create consumer groups for streams we consume
            streams = ["exposure", "session"]
            for stream in streams:
                try:
                    self.event_log.create_consumer_group(stream, self.consumer_group)
                except Exception as e:
                    logger.warning(f"⚠️ [{self.worker_name}] Consumer group creation warning: {e}")
            
            logger.info(f"✅ [{self.worker_name}] Connected to Redis")
            return True
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Failed to connect: {e}", exc_info=True)
            return False
    
    def load_risk_rules(self):
        """Load risk rules from YAML"""
        try:
            config_path = Path(__file__).parent.parent.parent / "config" / "risk_rules.yaml"
            with open(config_path, "r") as f:
                self.risk_rules = yaml.safe_load(f)
            logger.info(f"✅ [{self.worker_name}] Risk rules loaded")
            
            # Initialize policy decision table
            self.policy_table = PolicyDecisionTable(self.risk_rules)
            
            # Initialize Hard Exit Engine
            self.hard_exit_engine = HardExitEngine(self.risk_rules)
            
            logger.info(f"✅ [{self.worker_name}] Policy decision table and Hard Exit Engine initialized")
            
            # Initialize LT Band Controller
            self.lt_band_controller = LTBandController(self.risk_rules)
            logger.info(f"✅ [{self.worker_name}] LT Band Controller initialized")
            
            # Initialize Intent Arbiter
            self.intent_arbiter = IntentArbiter(self.risk_rules)
            logger.info(f"✅ [{self.worker_name}] Intent Arbiter initialized")
            
            # Initialize reporting trackers
            self.regime_logger = RegimeTransitionLogger()
            self.cap_recovery_tracker = CapRecoveryTracker()
            logger.info(f"✅ [{self.worker_name}] Reporting trackers initialized")
            
            # Initialize LT Trim Engine
            self.lt_trim_engine = LTTrimEngine(self.risk_rules)
            logger.info(f"✅ [{self.worker_name}] LT Trim Engine initialized")
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Failed to load risk rules: {e}", exc_info=True)
            # Use defaults
            self.risk_rules = {
                "exposure": {"max_gross_exposure_pct": 130.0, "soft_limit_pct": 120.0},
                "derisk": {
                    "soft_derisk": {"trigger_time": "16:15"},
                    "hard_derisk": {"trigger_time": "16:28", "reduction_target_pct": 100.0}
                }
            }
            self.policy_table = PolicyDecisionTable(self.risk_rules)
    
    def process_exposure_event(self, event_data: Dict[str, str]):
        """Process exposure event"""
        try:
            event = ExposureEvent.from_redis_stream(event_data)
            exposure_data = event.data
            
            self.latest_exposure = exposure_data
            
            # Update state store
            self.state_store.set_state("exposure", exposure_data)
            
            logger.debug(
                f"📊 [{self.worker_name}] Exposure updated: "
                f"gross={exposure_data.get('gross_exposure_pct', 0):.2f}%"
            )
            
            # Check if we need to generate intents
            self._evaluate_risk()
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error processing exposure event: {e}", exc_info=True)
    
    def process_session_event(self, event_data: Dict[str, str]):
        """Process session event"""
        try:
            event = SessionEvent.from_redis_stream(event_data)
            session_data = event.data
            
            self.latest_session = session_data
            
            # Update state store
            self.state_store.set_state("session", session_data)
            
            logger.debug(
                f"⏰ [{self.worker_name}] Session updated: "
                f"regime={session_data.get('regime')}, "
                f"minutes_to_close={session_data.get('minutes_to_close')}"
            )
            
            # Check if we need to generate intents
            self._evaluate_risk()
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error processing session event: {e}", exc_info=True)
    
    def _evaluate_risk(self):
        """Evaluate risk using policy decision table"""
        if not self.latest_exposure or not self.latest_session:
            return  # Need both to make decisions
        
        if not self.policy_table:
            logger.warning(f"⚠️ [{self.worker_name}] Policy table not initialized")
            return
        
        try:
            exposure_data = self.latest_exposure
            session_data = self.latest_session
            
            gross_exposure_pct = exposure_data.get("gross_exposure_pct", 0.0)
            regime = session_data.get("regime", "CLOSED")
            minutes_to_close = session_data.get("minutes_to_close")
            
            # Get bucket exposure
            buckets = exposure_data.get("buckets", {})
            lt_bucket = buckets.get("LT", {})
            mm_bucket = buckets.get("MM_PURE", {})
            
            lt_current_pct = lt_bucket.get("current_pct", 0.0)
            lt_potential_pct = lt_bucket.get("potential_pct", 0.0)
            mm_current_pct = mm_bucket.get("current_pct", 0.0)
            mm_potential_pct = mm_bucket.get("potential_pct", 0.0)
            
            # Calculate potential exposure (current + open orders)
            open_orders_potential = exposure_data.get("open_orders_potential", 0.0)
            potential_exposure_pct = gross_exposure_pct + (open_orders_potential / exposure_data.get("equity", 1.0)) * 100.0
            
            # Use policy decision table
            mode, reason = self.policy_table.decide(
                regime=regime,
                gross_exposure_pct=gross_exposure_pct,
                potential_exposure_pct=potential_exposure_pct,
                lt_current_pct=lt_current_pct,
                lt_potential_pct=lt_potential_pct,
                mm_current_pct=mm_current_pct,
                mm_potential_pct=mm_potential_pct,
                minutes_to_close=minutes_to_close
            )
            
            # Update current mode
            if mode != self.current_mode:
                logger.info(
                    f"🔄 [{self.worker_name}] Mode change: {self.current_mode} → {mode}: {reason}"
                )
                
                # Log mode transition
                if self.regime_logger:
                    from_mode = self.current_mode.value if hasattr(self.current_mode, 'value') else str(self.current_mode)
                    to_mode = mode.value if hasattr(mode, 'value') else str(mode)
                    self.regime_logger.log_mode_transition(
                        from_mode=from_mode,
                        to_mode=to_mode,
                        reason=reason,
                        exposure_data=exposure_data
                    )
                
                self.current_mode = mode
                # Update state store
                self.state_store.set_state("decision", {
                    "mode": mode.value,
                    "reason": reason,
                    "timestamp": time.time()
                })
            
            # Clear pending intents for this cycle
            self.pending_intents = []
            
            # Track if CAP_RECOVERY is active
            cap_recovery_active = False
            
            # Generate intents based on mode
            if mode == PolicyMode.HARD_DERISK:
                # At 130% cap, cancel risk-increasing orders first
                if gross_exposure_pct >= 130.0:
                    self._cancel_risk_increasing_orders()
                    cap_recovery_active = True
                    
                    # Start CAP_RECOVERY episode if not already active
                    if self.cap_recovery_tracker:
                        active_episode = self.cap_recovery_tracker.get_active_episode()
                        if not active_episode:
                            self.cap_recovery_tracker.start_episode(
                                gross_exposure_pct=gross_exposure_pct,
                                exposure_data=exposure_data
                            )
                    
                    # Generate CAP_RECOVERY intent instead of HARD_DERISK
                    cap_target = self.intent_arbiter.cap_recovery_target if self.intent_arbiter else 123.0
                    self._generate_derisk_intent("CAP_RECOVERY", gross_exposure_pct, cap_target, reason)
                else:
                    self._generate_derisk_intent("HARD_DERISK", gross_exposure_pct, 100.0, reason)
            elif mode == PolicyMode.SOFT_DERISK:
                soft_limit = self.risk_rules.get("exposure", {}).get("soft_limit_pct", 120.0)
                self._generate_derisk_intent("SOFT_DERISK", gross_exposure_pct, soft_limit, reason)
            elif mode == PolicyMode.THROTTLE_NEW_ORDERS:
                logger.info(f"⏸️ [{self.worker_name}] Throttling new orders: {reason}")
                # Don't generate intents, just log (throttling is handled by order gate)
            else:
                # NORMAL mode - check LT band drift
                self._check_lt_band_drift()
            
            # LT Trim Phase (Dedicated) - Runs for NORMAL and SOFT_DERISK
            # Suppressed ONLY by HARD_DERISK
            if mode != PolicyMode.HARD_DERISK:
                self._run_lt_trim_phase()

            # Check if CAP_RECOVERY should end (exposure dropped below target)
            if self.cap_recovery_tracker and cap_recovery_active:
                cap_target = self.intent_arbiter.cap_recovery_target if self.intent_arbiter else 123.0
                if gross_exposure_pct < cap_target:
                    # End CAP_RECOVERY episode
                    self.cap_recovery_tracker.end_episode(
                        gross_exposure_pct=gross_exposure_pct,
                        exposure_data=exposure_data
                    )
            
            # Arbitrate and publish intents
            if self.pending_intents and self.intent_arbiter:
                mode_str = mode.value if hasattr(mode, 'value') else str(mode)
                self._arbitrate_and_publish_intents(gross_exposure_pct, mode_str, self.pending_intents)
            elif self.pending_intents:
                # No arbiter, publish directly (fallback)
                for intent_data in self.pending_intents:
                    intent = IntentEvent.create(**intent_data)
                    self.event_log.publish("intents", intent)
                self.pending_intents = []
        
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error evaluating risk: {e}", exc_info=True)
    
    def _check_lt_band_drift(self):
        """Check LT band drift and generate corrective intents if needed"""
        if not self.latest_exposure or not self.lt_band_controller:
            return
        
        try:
            exposure_data = self.latest_exposure
            positions = exposure_data.get("positions", [])
            equity = exposure_data.get("equity", 1.0)
            gross_exposure_pct = exposure_data.get("gross_exposure_pct", 0.0)
            
            # Get LT bucket exposure
            buckets = exposure_data.get("buckets", {})
            lt_bucket = buckets.get("LT", {})
            lt_current = lt_bucket.get("current", 0.0)
            
            # Calculate LT long/short percentages (within LT bucket)
            # LT long/short pct = (LT long/short notional / equity) * 100
            # This is the percentage of total equity, not percentage within LT bucket
            lt_long_notional = sum(
                abs(p.get("notional", 0)) for p in positions 
                if p.get("bucket") == "LT" and p.get("quantity", 0) > 0
            )
            lt_short_notional = sum(
                abs(p.get("notional", 0)) for p in positions 
                if p.get("bucket") == "LT" and p.get("quantity", 0) < 0
            )
            
            # Calculate as percentage of equity (for band comparison)
            lt_long_pct = (lt_long_notional / equity) * 100.0 if equity > 0 else 0.0
            lt_short_pct = (lt_short_notional / equity) * 100.0 if equity > 0 else 0.0
            
            # Also calculate as percentage within LT bucket (for reference)
            lt_total = lt_long_notional + lt_short_notional
            if lt_total == 0:
                return  # No LT positions
            
            lt_long_pct_within_bucket = (lt_long_notional / lt_total) * 100.0 if lt_total > 0 else 0.0
            lt_short_pct_within_bucket = (lt_short_notional / lt_total) * 100.0 if lt_total > 0 else 0.0
            
            # Check band drift
            action_type, action_params = self.lt_band_controller.check_band_drift(
                lt_long_pct=lt_long_pct,
                lt_short_pct=lt_short_pct,
                gross_exposure_pct=gross_exposure_pct,
                positions=positions,
                equity=equity
            )
            
            if action_type and action_params:
                # Generate gentle corrective intent
                self._generate_lt_band_corrective_intent(
                    action_type, action_params, positions, equity, gross_exposure_pct
                )
        
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error checking LT band drift: {e}", exc_info=True)
    
    def _generate_lt_band_corrective_intent(
        self,
        action_type: str,
        action_params: Dict[str, Any],
        positions: List[Dict[str, Any]],
        equity: float,
        gross_exposure_pct: float
    ):
        """Generate gentle corrective intent for LT band drift"""
        try:
            prefer_classifications = action_params.get("prefer_classifications", [])
            avoid_classifications = action_params.get("avoid_classifications", [])
            
            # Select position for correction
            position = self.lt_band_controller.select_corrective_position(
                positions, prefer_classifications, avoid_classifications, equity
            )
            
            if not position:
                logger.debug(f"⚠️ [{self.worker_name}] No suitable position for LT band correction")
                return
            
            symbol = position.get("symbol", "UNKNOWN")
            quantity = position.get("quantity", 0)
            avg_price = position.get("avg_price", 1.0)
            
            # Determine action and classification based on action_type
            if "SHORT_TOO_HIGH" in action_type:
                # Prefer LT_SHORT_DECREASE: sell short position (BUY to close)
                if quantity < 0:
                    action = "BUY"  # Close short
                    classification = OrderClassification.LT_SHORT_DECREASE
                else:
                    # Or LT_LONG_INCREASE: buy long
                    action = "BUY"
                    classification = OrderClassification.LT_LONG_INCREASE
            elif "SHORT_TOO_LOW" in action_type:
                # Prefer LT_SHORT_INCREASE: sell to open short
                action = "SELL"
                classification = OrderClassification.LT_SHORT_INCREASE
            elif "LONG_TOO_HIGH" in action_type:
                # Prefer LT_LONG_DECREASE: sell long position
                if quantity > 0:
                    action = "SELL"  # Close long
                    classification = OrderClassification.LT_LONG_DECREASE
                else:
                    # Or LT_SHORT_INCREASE: sell to open short
                    action = "SELL"
                    classification = OrderClassification.LT_SHORT_INCREASE
            elif "LONG_TOO_LOW" in action_type:
                # Prefer LT_LONG_INCREASE: buy long
                action = "BUY"
                classification = OrderClassification.LT_LONG_INCREASE
            else:
                return  # Unknown action type
            
            # Calculate gentle corrective quantity
            corrective_qty = self.lt_band_controller.calculate_corrective_quantity(
                position, classification, equity, gross_exposure_pct
            )
            
            # Check if action would violate hard cap
            if classification.is_risk_increasing:
                risk_delta_notional = abs(corrective_qty * avg_price)
                risk_delta_gross_pct = (risk_delta_notional / equity) * 100.0
                if gross_exposure_pct + risk_delta_gross_pct > 130.0:
                    logger.warning(
                        f"⚠️ [{self.worker_name}] Corrective intent would violate hard cap, skipping"
                    )
                    return
            
            # Calculate risk delta
            if classification.is_risk_increasing:
                risk_delta_notional = abs(corrective_qty * avg_price)
            else:
                risk_delta_notional = -abs(corrective_qty * avg_price)
            risk_delta_gross_pct = (risk_delta_notional / equity) * 100.0
            
            # Position context
            position_context = {
                "current_qty": quantity,
                "avg_fill_price": avg_price,
                "notional": abs(position.get("notional", 0)),
            }
            
            # Use limit order near truth tick (stub: use avg_price ± $0.01)
            limit_price = None
            if self.lt_band_controller.use_limit_orders:
                if action == "BUY":
                    limit_price = avg_price + 0.01  # Slightly above
                else:
                    limit_price = avg_price - 0.01  # Slightly below
            
            # Generate low-priority corrective intent
            intent_data = {
                "intent_type": "LT_BAND_CORRECTIVE",
                "symbol": symbol,
                "action": action,
                "quantity": corrective_qty,
                "reason": f"LT band drift correction: {action_type}",
                "classification": classification.value,
                "bucket": "LT",
                "effect": classification.effect,
                "dir": classification.direction,
                "risk_delta_notional": risk_delta_notional,
                "risk_delta_gross_pct": risk_delta_gross_pct,
                "position_context_at_intent": position_context,
                "priority": 1,  # Low priority (gentle correction)
                "limit_price": limit_price,
            }
            
            # Add to pending intents (will be arbitrated later)
            self.pending_intents.append(intent_data)
            logger.debug(
                f"📝 [{self.worker_name}] Added LT band corrective intent to pending: "
                f"{action} {corrective_qty} {symbol} [{classification.value}]"
            )
        
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error generating LT band corrective intent: {e}", exc_info=True)
    
    def _run_lt_trim_phase(self):
        """
        LT Trim Phase - Dedicated mean-reversion reduction logic.
        Runs for NORMAL and SOFT_DERISK, suppressed ONLY by HARD_DERISK.
        """
        if not self.lt_trim_engine or not self.latest_exposure:
            return
        
        try:
            positions = self.latest_exposure.get("positions", [])
            regime = self.latest_session.get("regime", "NORMAL") if self.latest_session else "NORMAL"
            
            # Get L1 and Truth data
            l1_data, truth_data = self._fetch_market_data_snapshot(positions)
            
            for pos in positions:
                bucket = pos.get("bucket", "LT").upper()
                if bucket != "LT":
                    continue  # Skip non-LT positions
                
                symbol = pos.get("symbol")
                quantity = pos.get("quantity", 0)
                if not symbol or quantity == 0:
                    continue
                
                # Get market data for this symbol
                sym_l1 = l1_data.get(symbol, {})
                sym_truth = truth_data.get(symbol, {})
                
                # Call LT Trim Engine
                trim_intents = self.lt_trim_engine.plan_trim(
                    symbol=symbol,
                    position_qty=int(quantity),
                    l1_data=sym_l1,
                    truth_data=sym_truth,
                    regime=regime
                )
                
                if trim_intents:
                    self.pending_intents.extend(trim_intents)
                    logger.info(
                        f"🔻 [{self.worker_name}] LT Trim: {len(trim_intents)} intents for {symbol}"
                    )
        
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error in LT Trim phase: {e}", exc_info=True)

    def _arbitrate_and_publish_intents(
        self,
        current_gross_exposure_pct: float,
        current_mode: str,
        input_intents: Optional[List[Dict[str, Any]]] = None
    ):
        """Arbitrate pending intents and publish approved ones"""
        try:
            if not self.pending_intents:
                return
            
            # Store input intents for tracking
            input_intents_for_tracking = input_intents or self.pending_intents.copy()
            
            # Arbitrate
            arbitrated = self.intent_arbiter.arbitrate(
                intents=self.pending_intents,
                current_gross_exposure_pct=current_gross_exposure_pct,
                current_mode=current_mode
            )
            
            # Track arbitration (if IntentArbiter has tracker)
            if hasattr(self.intent_arbiter, 'tracker') and self.intent_arbiter.tracker:
                self.intent_arbiter.tracker.log_arbitration(
                    input_intents=input_intents_for_tracking,
                    output_intents=arbitrated,
                    current_gross_exposure_pct=current_gross_exposure_pct,
                    current_mode=current_mode
                )
            
            # Publish arbitrated intents
            for intent_data in arbitrated:
                intent = IntentEvent.create(**intent_data)
                msg_id = self.event_log.publish("intents", intent)
                if msg_id:
                    logger.info(
                        f"📤 [{self.worker_name}] Published arbitrated intent: "
                        f"{intent_data.get('intent_type')} {intent_data.get('action')} "
                        f"{intent_data.get('quantity')} {intent_data.get('symbol')} "
                        f"[{intent_data.get('classification')}]"
                    )
                else:
                    logger.warning(f"⚠️ [{self.worker_name}] Failed to publish arbitrated intent")
            
            # Clear pending intents
            self.pending_intents = []
        
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error arbitrating intents: {e}", exc_info=True)
            # Fallback: publish all pending intents
            for intent_data in self.pending_intents:
                try:
                    intent = IntentEvent.create(**intent_data)
                    self.event_log.publish("intents", intent)
                except Exception as e2:
                    logger.error(f"❌ [{self.worker_name}] Error publishing fallback intent: {e2}")
            self.pending_intents = []
    
    def _cancel_risk_increasing_orders(self):
        """Cancel risk-increasing open orders when cap reached"""
        try:
            # Publish cancel intent for all risk-increasing orders
            # This will be consumed by Execution Service
            # For now, we'll rely on Execution Service to track and cancel
            logger.warning(
                f"🚨 [{self.worker_name}] HARD CAP reached - "
                f"Execution Service should cancel all *_INCREASE orders"
            )
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error canceling risk-increasing orders: {e}", exc_info=True)
    
    def _determine_classification(self, position: Dict[str, Any], action: str, quantity: int) -> OrderClassification:
        """Determine classification from position and action"""
        # Get bucket from position (default to LT if not specified)
        bucket = position.get("bucket", "LT").upper()
        if bucket not in ["LT", "MM"]:
            bucket = "LT"  # Default to LT
        
        # Determine direction: LONG if quantity > 0, SHORT if quantity < 0
        # For derisk: if closing long (SELL), direction is LONG; if closing short (BUY), direction is SHORT
        current_qty = position.get("quantity", 0)
        if current_qty > 0:
            direction = "LONG"
        elif current_qty < 0:
            direction = "SHORT"
        else:
            # No position - determine from action
            direction = "LONG" if action == "BUY" else "SHORT"
        
        # Effect: DECREASE (we're reducing/closing position)
        effect = "DECREASE"
        
        return OrderClassification.from_components(bucket, direction, effect)
    
    def _fetch_market_data_snapshot(self, positions: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Fetch L1 and Truth data for positions from Redis.
        Returns (l1_data, truth_data)
        """
        l1_data = {}
        truth_data = {}
        
        if not positions or not self.state_store:
            return l1_data, truth_data
            
        try:
            # We iterate positions to get symbols
            # Assuming keys: 'l1:{symbol}' or similar for L1.
            # And 'truth:{symbol}' for Truth metrics.
            # If not found, use MarkPrice from position loop fallback internally in HardExitEngine,
            # but here we try to populate what we can.
            
            # Optimization: Pipelined fetch could be better, but loop is fine for rare HARD_DERISK.
            for pos in positions:
                sym = pos.get("symbol")
                if not sym: continue
                
                # Fetch L1
                # Standard convention check? Or assuming simple keys.
                # If MarketDataEngine is not standard, we might get misses.
                # Use StateStore if stored as state, else raw redis.
                # Try raw redis for keys like "ticker:{sym}" or "quote:{sym}"?
                # Without explicit knowledge, I will rely on positions['mark_price'] usually found in naive engines.
                # BUT HardExitEngine needs Bid/Ask for spread.
                
                # Let's try fetching "state:l1:{sym}" via StateStore which adds prefix "state:"
                # If MarketDataEngine writes "state:l1:AAPL", then store.get_state("l1:AAPL")                # Fetch L1
                l1_state = self.state_store.get_state(f"l1:{sym}")
                if l1_state:
                    l1_data[sym] = l1_state
                
                # Non-Invasive: Fetch V2 for comparison if canary
                canary_symbols = self.risk_rules.get("feature_flags", {}).get("canary", {}).get("symbols", [])
                if sym in canary_symbols:
                    v2_state = self.state_store.get_state(f"snapshot_cache_v2:{sym}")
                    if v2_state and sym in l1_data:
                        l1_data[sym]['v2_snapshot'] = v2_state
                
                # Fetch Truth
                truth_state = self.state_store.get_state(f"truth:{sym}")
                if truth_state:
                    truth_data[sym] = truth_state
                    
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error fetching market data: {e}")
            
        return l1_data, truth_data

    def _generate_derisk_intent(self, intent_type: str, current_exposure: float, target_exposure: float, reason: str):
        """Generate de-risk intent with full classification"""
        try:
            if not self.latest_exposure:
                return
            
            positions = self.latest_exposure.get("positions", [])
            if not positions:
                logger.warning(f"⚠️ [{self.worker_name}] No positions to derisk")
                return
            
            # Strategy: reduce largest position first
            # In production, use truth tick proximity, dominant print zones, etc.
            largest_position = max(positions, key=lambda p: abs(p.get("notional", 0)))
            symbol = largest_position.get("symbol", "UNKNOWN")
            quantity = largest_position.get("quantity", 0)
            
            if quantity == 0:
                return
            
            # Calculate reduction needed
            exposure_reduction_pct = current_exposure - target_exposure
            if exposure_reduction_pct <= 0:
                return  # Already at or below target
            
            # Reduce by chunk (10% for HARD_DERISK, smaller for SOFT_DERISK)
            # Reduce by chunk (10% for HARD_DERISK, smaller for SOFT_DERISK)
            if intent_type == "HARD_DERISK":
                # Use Preference Engine for HARD_DERISK
                if self.hard_exit_engine:
                    try:
                        # Fetch Market Data Snapshot
                        l1_data, truth_data = self._fetch_market_data_snapshot(positions)
                        
                        # Determine Time Regime
                        # If CLOSE <= 2m -> "CLOSE", else "LATE" (Standard Hard Derisk)
                        time_regime = "LATE"
                        minutes_to_close = self.latest_session.get("minutes_to_close", 15)
                        if minutes_to_close <= 2:
                            time_regime = "CLOSE"
                            
                        # Calculate Reduction Amount
                        # Target is provided as pct of equity.
                        # target_exposure is % (e.g. 100.0). current is gross_exposure_pct.
                        equity = self.latest_exposure.get("equity", 1.0)
                        pct_to_reduce = max(0, current_exposure - target_exposure)
                        notional_to_reduce = (pct_to_reduce / 100.0) * equity
                        
                        if notional_to_reduce > 0:
                            # Verify Confidence API availability? HardExitEngine takes map.
                            # We don't have explicit confidence stream in DecisionEngine. Use placeholder/default.
                            confidence_scores = {} # Empty = Default 100
                            
                            # Call Engine
                            intents = self.hard_exit_engine.plan_hard_derisk(
                                reduction_notional=notional_to_reduce,
                                positions=positions,
                                l1_data=l1_data,
                                truth_data=truth_data,
                                regime=time_regime,
                                mode=intent_type, # "HARD_DERISK"
                                confidence_scores=confidence_scores,
                                rules=self.risk_rules
                            )
                            
                            if intents:
                                logger.info(f"⚡ [{self.worker_name}] HardExitEngine generated {len(intents)} intents ({time_regime})")
                                self.pending_intents.extend(intents)
                                return
                            else:
                                logger.warning(f"⚠️ [{self.worker_name}] HardExitEngine returned no intents for {notional_to_reduce} reduction")
                                # Fallback to naive implementation if empty?
                                pass
                                
                    except Exception as e:
                        logger.error(f"❌ [{self.worker_name}] HardExitEngine failed: {e}", exc_info=True)
                        # Fallback to naive logic below
                
                chunk_pct = 0.10  # 10% per step (Fallback)
                target_reduction_pct = current_exposure - target_exposure # Logic reuse
            else:
                chunk_pct = 0.05  # 5% for soft derisk
            
            # Calculate quantity to reduce
            position_notional = abs(largest_position.get("notional", 0))
            equity = self.latest_exposure.get("equity", 1.0)
            reduction_notional = (exposure_reduction_pct / 100.0) * equity * chunk_pct
            
            # Convert to shares
            avg_price = largest_position.get("avg_price", 1.0)
            reduce_quantity = int(reduction_notional / avg_price) if avg_price > 0 else 0
            
            # Ensure we don't reduce more than position size
            reduce_quantity = min(reduce_quantity, abs(quantity))
            
            if reduce_quantity == 0:
                reduce_quantity = 1  # At least 1 share
            
            action = "SELL" if quantity > 0 else "BUY"  # Close long = sell, close short = buy
            
            # Determine classification
            classification = self._determine_classification(largest_position, action, reduce_quantity)
            bucket = classification.bucket
            direction = classification.direction
            effect = classification.effect
            
            # Calculate risk delta (worst-case change if filled)
            # For DECREASE, this reduces exposure, so risk_delta is negative
            risk_delta_notional = -abs(reduce_quantity * avg_price)  # Negative = reduces exposure
            risk_delta_gross_pct = (risk_delta_notional / equity) * 100.0
            
            # Position context snapshot
            position_context = {
                "current_qty": quantity,
                "avg_fill_price": avg_price,
                "notional": position_notional,
            }
            
            # For SOFT_DERISK, use limit price near "truth tick" (stub: use avg_price ± $0.01)
            limit_price = None
            if intent_type == "SOFT_DERISK":
                if action == "SELL":
                    limit_price = avg_price - 0.01  # Hit bid (below avg)
                else:
                    limit_price = avg_price + 0.01  # Hit ask (above avg)
            
            intent_data = {
                "intent_type": intent_type,
                "symbol": symbol,
                "action": action,
                "quantity": reduce_quantity,
                "reason": reason,
                "classification": classification.value,
                "bucket": bucket,
                "effect": effect,
                "dir": direction,
                "risk_delta_notional": risk_delta_notional,
                "risk_delta_gross_pct": risk_delta_gross_pct,
                "position_context_at_intent": position_context,
                "priority": 10 if intent_type == "HARD_DERISK" else 5,
                "limit_price": limit_price,
            }
            
            # Add to pending intents (will be arbitrated later)
            self.pending_intents.append(intent_data)
            logger.debug(
                f"📝 [{self.worker_name}] Added {intent_type} intent to pending: "
                f"{action} {reduce_quantity} {symbol} [{classification.value}]"
            )
        
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error generating derisk intent: {e}", exc_info=True)
    
    def run(self):
        """Main engine loop"""
        try:
            logger.info(f"🚀 [{self.worker_name}] Starting...")
            
            if not self.connect():
                logger.error(f"❌ [{self.worker_name}] Cannot start: connection failed")
                return
            
            self.load_risk_rules()
            
            self.running = True
            logger.info(f"✅ [{self.worker_name}] Started (consumer: {self.consumer_name})")
            
            # Main loop - read from streams
            while self.running:
                try:
                    # Read from exposure stream
                    exposure_messages = self.event_log.read(
                        "exposure", self.consumer_group, self.consumer_name,
                        count=10, block=1000
                    )
                    for msg in exposure_messages:
                        # msg["data"] is already a dict from Redis Stream
                        self.process_exposure_event(msg["data"])
                        self.event_log.ack("exposure", self.consumer_group, msg["message_id"])
                    
                    # Read from session stream
                    session_messages = self.event_log.read(
                        "session", self.consumer_group, self.consumer_name,
                        count=10, block=1000
                    )
                    for msg in session_messages:
                        # msg["data"] is already a dict from Redis Stream
                        self.process_session_event(msg["data"])
                        self.event_log.ack("session", self.consumer_group, msg["message_id"])
                
                except Exception as e:
                    logger.error(f"❌ [{self.worker_name}] Error in main loop: {e}", exc_info=True)
                    time.sleep(1)
        
        except KeyboardInterrupt:
            logger.info(f"🛑 [{self.worker_name}] Stopped by user")
        except Exception as e:
            logger.error(f"❌ [{self.worker_name}] Error: {e}", exc_info=True)
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Cleanup resources"""
        self.running = False
        logger.info(f"✅ [{self.worker_name}] Cleanup completed")


def main():
    """Main entry point"""
    engine = DecisionEngine()
    
    def signal_handler(sig, frame):
        logger.info(f"🛑 [{engine.worker_name}] Received SIGINT, shutting down...")
        engine.running = False
    
    signal.signal(signal.SIGINT, signal_handler)
    engine.run()


if __name__ == "__main__":
    main()

