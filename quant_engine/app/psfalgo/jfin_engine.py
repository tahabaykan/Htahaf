"""
JFIN Engine - Deterministic Transformer for ADDNEWPOS

⚠️ CRITICAL DESIGN PRINCIPLES:
1. JFIN is NOT a decision engine - it's a DETERMINISTIC TRANSFORMER
2. JFIN runs AFTER ADDNEWPOS decision engine
3. JFIN output is INTENTIONS, NOT orders (Human-in-the-Loop)
4. Orders are NEVER sent directly - only previewed for approval
5. BB/FB/SAS/SFS pools are STRICTLY SEPARATE
6. Lot distribution → Addable lot clipping → Intent generation (ORDER MATTERS!)

Flow:
    ADDNEWPOS Decision → JFIN Transformer → Intentions → User Approval → Orders

Parameters (adjustable via Rules Window):
    - selection_percent: %10, %12, %15 (TUMCSV version)
    - percentage: %25, %50, %75, %100 (lot percentage)
    - exposure_percent: %60 default (max exposure usage)
    - alpha: 3 (lot distribution weight)
    - min_selection: 2 (minimum stocks per group)
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
import math

from app.core.logger import logger


class JFINScoreType(Enum):
    """JFIN Score Types - 4 separate pools"""
    BB_LONG = "BB_LONG"      # Bid Buy - Long positions (highest Final_BB_skor)
    FB_LONG = "FB_LONG"      # Front Buy - Long positions (highest Final_FB_skor)
    SAS_SHORT = "SAS_SHORT"  # Ask Sell - Short positions (lowest Final_SAS_skor)
    SFS_SHORT = "SFS_SHORT"  # Soft Front Sell - Short positions (lowest Final_SFS_skor)


class JFINOrderType(Enum):
    """JFIN Order Types for price calculation"""
    BB = "BB"       # Bid Buy: bid + (spread * 0.15)
    FB = "FB"       # Front Buy: last + 0.01
    SAS = "SAS"     # Ask Sell: ask - (spread * 0.15)
    SFS = "SFS"     # Front Sell: last - 0.01


@dataclass
class JFINConfig:
    """
    JFIN Configuration - All parameters adjustable via Rules Window
    """
    # TUMCSV Selection Parameters
    selection_percent: float = 0.10      # %10 default (V10TUMCSV)
    min_selection: int = 2               # Minimum stocks per group
    heldkuponlu_pair_count: int = 8      # Special rule for HELDKUPONLU group
    
    # Janall Selection Criteria (Two-Step Intersection)
    long_percent: float = 25.0           # Top %X for LONG (Janall: 25%)
    long_multiplier: float = 1.5         # Average × multiplier for LONG (Janall: 1.5x)
    short_percent: float = 25.0          # Bottom %X for SHORT (Janall: 25%)
    short_multiplier: float = 0.7        # Average × multiplier for SHORT (Janall: 0.7x)
    max_short: int = 3                   # Maximum SHORT stocks per group (Janall: 3)
    
    # Company Limit (Janall: limit_by_company)
    company_limit_enabled: bool = True   # Enable company limit (Janall: /1.6 rule)
    company_limit_divisor: float = 1.6   # Janall: max = total / 1.6
    
    # Lot Distribution Parameters
    alpha: float = 3.0                   # Alpha coefficient for lot weighting
    total_long_rights: int = 28000       # Total long lot rights
    total_short_rights: int = 12000      # Total short lot rights
    
    # JFIN Percentage (adjustable: 25, 50, 75, 100)
    jfin_percentage: int = 50            # Default %50
    
    # Exposure Parameters
    exposure_percent: float = 60.0       # Max exposure usage (%)
    
    # Minimum Lot Controls
    min_lot_per_order: int = 200         # Minimum 200 lot per order
    lot_rounding: int = 100              # Round to 100s
    
    # Pool Separation (CRITICAL: must stay True)
    separate_pools: bool = True          # BB/FB/SAS/SFS pools are SEPARATE
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class JFINStock:
    """
    JFIN Stock - Selected stock with calculated lots
    """
    symbol: str
    group: str                           # PRIMARY GROUP
    cgrup: Optional[str] = None          # SECONDARY GROUP (CGRUP)
    score_type: JFINScoreType = JFINScoreType.BB_LONG
    
    # Scores
    final_bb_skor: float = 0.0
    final_fb_skor: float = 0.0
    final_sas_skor: float = 0.0
    final_sfs_skor: float = 0.0
    fbtot: float = 0.0
    sfstot: float = 0.0
    gort: float = 0.0
    sma63_chg: float = 0.0
    
    # Lot Calculations (ORDER MATTERS!)
    # Step 1: Group-weighted lot
    calculated_lot: int = 0
    # Step 2: Addable lot (after MAXALW, position, daily limit checks)
    addable_lot: int = 0
    # Step 3: Final lot (after percentage and exposure adjustments)
    final_lot: int = 0
    
    # Position Data
    maxalw: int = 0
    current_position: int = 0
    befday_qty: int = 0
    
    # Market Data (for price calculation)
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    
    # Calculated Price
    order_price: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['score_type'] = self.score_type.value
        return result


@dataclass
class JFINIntent:
    """
    JFIN Intent - Output of JFIN transformer
    
    ⚠️ THIS IS NOT AN ORDER!
    This is an INTENTION that requires user approval before execution.
    """
    id: str
    symbol: str
    group: str
    cgrup: Optional[str]
    score_type: str                      # BB_LONG, FB_LONG, SAS_SHORT, SFS_SHORT
    order_type: str                      # BB, FB, SAS, SFS
    action: str                          # BUY or SELL
    qty: int                             # Final lot quantity
    price: float                         # Calculated price
    
    # Audit Trail
    calculated_lot: int                  # Original calculated lot
    addable_lot: int                     # After MAXALW/position clipping
    percentage_applied: int              # %25, %50, %75, %100
    exposure_adjusted: bool              # Was exposure adjustment applied?
    
    # Scores (for transparency)
    score: float                         # Primary score used for selection
    fbtot: float = 0.0
    sfstot: float = 0.0
    gort: float = 0.0
    
    # Position Context
    maxalw: int = 0
    current_position: int = 0
    befday_qty: int = 0
    
    # Status
    status: str = "PENDING"              # PENDING, APPROVED, REJECTED, EXPIRED
    created_at: datetime = field(default_factory=datetime.now)
    
    # Reason
    reason_code: str = ""
    reason_text: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result['created_at'] = self.created_at.isoformat()
        return result


@dataclass
class JFINResult:
    """
    JFIN Transformer Result
    
    Contains 4 SEPARATE pools of intentions (BB/FB/SAS/SFS)
    """
    # Separate pools (CRITICAL: must stay separate)
    bb_long_intents: List[JFINIntent] = field(default_factory=list)
    fb_long_intents: List[JFINIntent] = field(default_factory=list)
    sas_short_intents: List[JFINIntent] = field(default_factory=list)
    sfs_short_intents: List[JFINIntent] = field(default_factory=list)
    
    # Summary
    total_intents: int = 0
    total_long_lots: int = 0
    total_short_lots: int = 0
    
    # Config used
    config: Optional[JFINConfig] = None
    
    # Timing
    execution_time_ms: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Errors
    errors: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        """Calculate totals"""
        self.total_intents = (
            len(self.bb_long_intents) + 
            len(self.fb_long_intents) + 
            len(self.sas_short_intents) + 
            len(self.sfs_short_intents)
        )
        self.total_long_lots = (
            sum(i.qty for i in self.bb_long_intents) +
            sum(i.qty for i in self.fb_long_intents)
        )
        self.total_short_lots = (
            sum(i.qty for i in self.sas_short_intents) +
            sum(i.qty for i in self.sfs_short_intents)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'bb_long_intents': [i.to_dict() for i in self.bb_long_intents],
            'fb_long_intents': [i.to_dict() for i in self.fb_long_intents],
            'sas_short_intents': [i.to_dict() for i in self.sas_short_intents],
            'sfs_short_intents': [i.to_dict() for i in self.sfs_short_intents],
            'total_intents': self.total_intents,
            'total_long_lots': self.total_long_lots,
            'total_short_lots': self.total_short_lots,
            'config': self.config.to_dict() if self.config else None,
            'execution_time_ms': self.execution_time_ms,
            'timestamp': self.timestamp.isoformat(),
            'errors': self.errors
        }


class JFINEngine:
    """
    JFIN Engine - Deterministic Transformer
    
    ⚠️ CRITICAL:
    - This is NOT a decision engine
    - Output is INTENTIONS, not orders
    - Orders are NEVER sent directly
    - BB/FB/SAS/SFS pools are STRICTLY SEPARATE
    """
    
    def __init__(self, config: Optional[JFINConfig] = None):
        self.config = config or JFINConfig()
        self._group_weights: Dict[str, Dict[str, float]] = {
            'long': {},
            'short': {}
        }
        logger.info(f"[JFIN] Engine initialized with config: {self.config.to_dict()}")
    
    def update_config(self, new_config: Dict[str, Any]):
        """
        Update JFIN config from Rules Window
        
        This allows users to adjust parameters like:
        - jfin_percentage: 25, 50, 75, 100
        - selection_percent: 0.10, 0.12, 0.15
        - exposure_percent: 0-100
        - alpha: 1-5
        """
        for key, value in new_config.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                logger.info(f"[JFIN] Config updated: {key} = {value}")
    
    def set_group_weights(self, long_weights: Dict[str, float], short_weights: Dict[str, float]):
        """Set group weights from CSV or UI"""
        self._group_weights['long'] = long_weights
        self._group_weights['short'] = short_weights
        logger.info(f"[JFIN] Group weights set: {len(long_weights)} long, {len(short_weights)} short")
    
    async def transform(
        self,
        addnewpos_candidates: List[Dict[str, Any]],
        market_data: Dict[str, Dict[str, Any]],
        positions: Dict[str, Dict[str, Any]],
        befday_positions: Dict[str, int],
        max_addable_total: Optional[int] = None
    ) -> JFINResult:
        """
        Transform ADDNEWPOS candidates into JFIN Intentions
        
        ⚠️ THIS DOES NOT SEND ORDERS!
        Output is a list of INTENTIONS for user approval.
        
        Args:
            addnewpos_candidates: Candidates from ADDNEWPOS decision engine
            market_data: Current market data (bid, ask, last)
            positions: Current positions
            befday_positions: BEFDAY positions (for daily limit)
            max_addable_total: Max addable lot (Pot Max - Pot Total)
        
        Returns:
            JFINResult with 4 separate pools of intentions
        """
        start_time = datetime.now()
        errors = []
        
        try:
            logger.info(f"[JFIN] 🔄 Transform started with {len(addnewpos_candidates)} candidates")
            
            # Step 1: TUMCSV Selection - Select stocks for each pool
            try:
                with open("logs/jfin_reasoning.txt", "w", encoding="utf-8") as f:
                    f.write(f"JFIN Transform Started at {datetime.now()}\\n")
                    f.write(f"Input Candidates: {len(addnewpos_candidates)}\\n")
                    if addnewpos_candidates:
                        f.write(f"First 3 Candidates: {str(addnewpos_candidates[:3])}\\n")
                    else:
                        f.write("WARNING: No candidates provided to JFIN! Check ADDNEWPOS engine output.\\n")
            except Exception as e:
                logger.error(f"Failed to write initial debug log: {e}")

            bb_stocks, fb_stocks, sas_stocks, sfs_stocks = self._select_stocks_for_pools(
                addnewpos_candidates
            )
            
            logger.info(f"[JFIN] 📊 Selection: BB={len(bb_stocks)}, FB={len(fb_stocks)}, SAS={len(sas_stocks)}, SFS={len(sfs_stocks)}")
            
            # Step 2: Lot Distribution - Calculate lots for each stock
            bb_stocks = self._distribute_lots(bb_stocks, 'long')
            fb_stocks = self._distribute_lots(fb_stocks, 'long')
            sas_stocks = self._distribute_lots(sas_stocks, 'short')
            sfs_stocks = self._distribute_lots(sfs_stocks, 'short')
            
            # Step 3: Addable Lot Calculation - Clip to MAXALW, position, daily limit
            bb_stocks = self._calculate_addable_lots(bb_stocks, positions, befday_positions)
            fb_stocks = self._calculate_addable_lots(fb_stocks, positions, befday_positions)
            sas_stocks = self._calculate_addable_lots(sas_stocks, positions, befday_positions)
            sfs_stocks = self._calculate_addable_lots(sfs_stocks, positions, befday_positions)
            
            # Step 4: Apply JFIN Percentage and Exposure Adjustment
            bb_stocks = self._apply_percentage_and_exposure(bb_stocks, max_addable_total, 'long')
            fb_stocks = self._apply_percentage_and_exposure(fb_stocks, max_addable_total, 'long')
            sas_stocks = self._apply_percentage_and_exposure(sas_stocks, max_addable_total, 'short')
            sfs_stocks = self._apply_percentage_and_exposure(sfs_stocks, max_addable_total, 'short')
            
            # Step 5: Calculate Prices
            bb_stocks = self._calculate_prices(bb_stocks, market_data, JFINOrderType.BB)
            fb_stocks = self._calculate_prices(fb_stocks, market_data, JFINOrderType.FB)
            sas_stocks = self._calculate_prices(sas_stocks, market_data, JFINOrderType.SAS)
            sfs_stocks = self._calculate_prices(sfs_stocks, market_data, JFINOrderType.SFS)
            
            # Step 6: Generate Intentions (NOT orders!)
            bb_intents = self._generate_intents(bb_stocks, JFINScoreType.BB_LONG, JFINOrderType.BB)
            fb_intents = self._generate_intents(fb_stocks, JFINScoreType.FB_LONG, JFINOrderType.FB)
            sas_intents = self._generate_intents(sas_stocks, JFINScoreType.SAS_SHORT, JFINOrderType.SAS)
            sfs_intents = self._generate_intents(sfs_stocks, JFINScoreType.SFS_SHORT, JFINOrderType.SFS)
            
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            
            result = JFINResult(
                bb_long_intents=bb_intents,
                fb_long_intents=fb_intents,
                sas_short_intents=sas_intents,
                sfs_short_intents=sfs_intents,
                config=self.config,
                execution_time_ms=execution_time,
                errors=errors
            )
            
            logger.info(
                f"[JFIN] ✅ Transform completed: {result.total_intents} intents "
                f"(Long: {result.total_long_lots} lots, Short: {result.total_short_lots} lots) "
                f"in {execution_time:.2f}ms"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"[JFIN] ❌ Transform error: {e}", exc_info=True)
            errors.append(str(e))
            return JFINResult(errors=errors)
    
    def _select_stocks_for_pools(
        self,
        candidates: List[Dict[str, Any]]
    ) -> Tuple[List[JFINStock], List[JFINStock], List[JFINStock], List[JFINStock]]:
        """
        Step 1: TUMCSV Selection - JANALL BIREBIR MANTIK
        
        Select stocks using Janall's exact logic:
        1. Two-criteria intersection (Average×Multiplier + Top%X)
        2. Company limit (limit_by_company: max = total / 1.6)
        3. HELDKUPONLU special logic (CGRUP-based selection)
        
        ⚠️ POOLS ARE SEPARATE - same stock can appear in multiple pools
        """
        bb_stocks = []
        fb_stocks = []
        sas_stocks = []
        sfs_stocks = []
        
        # Group candidates by PRIMARY GROUP
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for candidate in candidates:
            group = candidate.get('group', candidate.get('GROUP', 'UNKNOWN'))
            if group not in groups:
                groups[group] = []
            groups[group].append(candidate)
        
        # Process LONG groups
        for group_name, weight in self._group_weights.get('long', {}).items():
            if weight <= 0:
                continue
            
            group_candidates = groups.get(group_name, [])
            if not group_candidates:
                continue
            
            # HELDKUPONLU special logic
            if group_name.upper() == 'HELDKUPONLU':
                bb_long_held, fb_long_held, sas_short_held, sfs_short_held = self._select_heldkuponlu_stocks(
                    group_candidates, group_name
                )
                bb_stocks.extend(bb_long_held)
                fb_stocks.extend(fb_long_held)
                sas_stocks.extend(sas_short_held)
                sfs_stocks.extend(sfs_short_held)
                continue
            
            # Normal groups: Janall two-step selection with intersection
            # BB Long: FB → BB two-step
            bb_selected = self._select_stocks_janall_logic(
                group_candidates, 'Final_FB_skor', 'Final_BB_skor', 'LONG', group_name
            )
            for c in bb_selected:
                stock = self._candidate_to_jfin_stock(c, group_name, JFINScoreType.BB_LONG)
                bb_stocks.append(stock)
            
            # FB Long: Just Final_FB_skor (highest)
            fb_selected = self._select_stocks_janall_logic(
                group_candidates, 'Final_FB_skor', None, 'LONG', group_name
            )
            for c in fb_selected:
                stock = self._candidate_to_jfin_stock(c, group_name, JFINScoreType.FB_LONG)
                fb_stocks.append(stock)
        
        # Process SHORT groups
        for group_name, weight in self._group_weights.get('short', {}).items():
            if weight <= 0:
                continue
            
            # HELDKUPONLU already processed in LONG section
            if group_name.upper() == 'HELDKUPONLU':
                continue
            
            group_candidates = groups.get(group_name, [])
            if not group_candidates:
                continue
            
            # SAS Short: Final_SAS_skor (lowest)
            sas_selected = self._select_stocks_janall_logic(
                group_candidates, 'Final_SAS_skor', None, 'SHORT', group_name
            )
            for c in sas_selected:
                stock = self._candidate_to_jfin_stock(c, group_name, JFINScoreType.SAS_SHORT)
                sas_stocks.append(stock)
            
            # SFS Short: Final_SFS_skor (lowest)
            sfs_selected = self._select_stocks_janall_logic(
                group_candidates, 'Final_SFS_skor', None, 'SHORT', group_name
            )
            for c in sfs_selected:
                stock = self._candidate_to_jfin_stock(c, group_name, JFINScoreType.SFS_SHORT)
                sfs_stocks.append(stock)
        
        logger.info(
            f"[JFIN] Selection complete: BB={len(bb_stocks)}, FB={len(fb_stocks)}, "
            f"SAS={len(sas_stocks)}, SFS={len(sfs_stocks)}"
        )
        
        return bb_stocks, fb_stocks, sas_stocks, sfs_stocks
    
    def _select_stocks_janall_logic(
        self,
        candidates: List[Dict[str, Any]],
        primary_score: str,
        secondary_score: Optional[str],
        direction: str,  # 'LONG' or 'SHORT'
        group_name: str
    ) -> List[Dict[str, Any]]:
        """
        Janall's exact selection logic: Two-criteria intersection + Company limit
        
        Args:
            candidates: Group candidates
            primary_score: Primary score column (e.g., 'Final_FB_skor')
            secondary_score: Secondary score column (e.g., 'Final_BB_skor') or None
            direction: 'LONG' or 'SHORT'
            group_name: Group name for logging
        
        Returns:
            Selected candidates (after intersection + company limit)
        """
        if not candidates:
            return []
        
        # Get valid candidates with primary score (check both uppercase and lowercase)
        valid_candidates = []
        for c in candidates:
            score_val = c.get(primary_score) or c.get(primary_score.lower(), None)
            if score_val is not None and not (isinstance(score_val, float) and math.isnan(score_val)):
                valid_candidates.append(c)
        
        if not valid_candidates:
            logger.debug(f"[JFIN] Group {group_name}: No valid {primary_score} found")
            return []
        
        # Extract scores for calculation
        score_values = []
        for c in valid_candidates:
            score = c.get(primary_score) or c.get(primary_score.lower(), 0.0) or 0.0
            if isinstance(score, (int, float)) and not math.isnan(score):
                score_values.append(float(score))
        
        if not score_values:
            logger.debug(f"[JFIN] Group {group_name}: No numeric {primary_score} values")
            return []
        
        # Calculate average
        avg_score = sum(score_values) / len(score_values)
        
        # Janall rules
        if direction == 'LONG':
            multiplier = self.config.long_multiplier
            percent = self.config.long_percent
            # Criterion 1: Average × multiplier (higher is better)
            threshold = avg_score * multiplier
            criterion1_candidates = []
            for c in valid_candidates:
                score = c.get(primary_score) or c.get(primary_score.lower(), 0.0) or 0.0
                if isinstance(score, (int, float)) and not math.isnan(score) and float(score) >= threshold:
                    criterion1_candidates.append(c)
            # Criterion 2: Top %X
            top_count = max(1, int(math.ceil(len(valid_candidates) * percent / 100)))
            criterion2_candidates = sorted(
                valid_candidates,
                key=lambda x: float(x.get(primary_score, x.get(primary_score.lower(), 0)) or 0),
                reverse=True
            )[:top_count]
        else:  # SHORT
            multiplier = self.config.short_multiplier
            percent = self.config.short_percent
            # Criterion 1: Average × multiplier (lower is better)
            threshold = avg_score * multiplier
            criterion1_candidates = []
            for c in valid_candidates:
                score = c.get(primary_score) or c.get(primary_score.lower(), 0.0) or 0.0
                if isinstance(score, (int, float)) and not math.isnan(score) and float(score) <= threshold:
                    criterion1_candidates.append(c)
            # Criterion 2: Bottom %X
            bottom_count = max(1, int(math.ceil(len(valid_candidates) * percent / 100)))
            criterion2_candidates = sorted(
                valid_candidates,
                key=lambda x: float(x.get(primary_score, x.get(primary_score.lower(), 0)) or 0),
                reverse=False
            )[:bottom_count]
        
        # Intersection of two criteria (Janall logic)
        criterion1_symbols = {c.get('symbol', c.get('PREF_IBKR', c.get('PREF IBKR', ''))) for c in criterion1_candidates}
        criterion2_symbols = {c.get('symbol', c.get('PREF_IBKR', c.get('PREF IBKR', ''))) for c in criterion2_candidates}
        intersection_symbols = criterion1_symbols.intersection(criterion2_symbols)
        
        intersection_candidates = [
            c for c in valid_candidates
            if c.get('symbol', c.get('PREF_IBKR', c.get('PREF IBKR', ''))) in intersection_symbols
        ]
        
        # Log detailed reasoning to file for user transparency
        try:
            with open("logs/jfin_reasoning.txt", "a", encoding="utf-8") as f:
                f.write(f"\\n{'='*50}\\n")
                f.write(f"GROUP: {group_name} | DIRECTION: {direction} | SCORE: {primary_score}\\n")
                f.write(f"STATS: Avg={avg_score:.4f} | Multiplier={multiplier} | Threshold={threshold:.4f}\\n")
                f.write(f"CRITERIA: Top/Bottom %{percent} (Count: {len(criterion2_candidates)})\\n")
                f.write(f"{'-'*50}\\n")
                
                # Log detailed check for each valid candidate
                for c in valid_candidates:
                    sym = c.get('symbol', c.get('PREF_IBKR', 'Unknown'))
                    score = float(c.get(primary_score) or c.get(primary_score.lower(), 0) or 0)
                    
                    # Check Criterion 1 (Threshold)
                    pass_c1 = False
                    if direction == 'LONG':
                        pass_c1 = score >= threshold
                        c1_reason = f"{score:.4f} >= {threshold:.4f}"
                    else:
                        pass_c1 = score <= threshold
                        c1_reason = f"{score:.4f} <= {threshold:.4f}"
                    
                    # Check Criterion 2 (Rank)
                    # Note: criterion2_candidates is just a list, checking membership
                    is_in_c2 = c in criterion2_candidates
                    
                    status = "REJECTED"
                    reason = []
                    if not pass_c1:
                        reason.append(f"Failed Threshold ({c1_reason})")
                    if not is_in_c2:
                        reason.append(f"Failed Rank (Not in Top/Bottom {percent}%)")
                    
                    if pass_c1 and is_in_c2:
                        status = "SELECTED"
                        reason = ["Passed Both Criteria"]
                    
                    f.write(f"  {sym:<8} | Score: {score:<8.4f} | {status} | Reason: {', '.join(reason)}\\n")
        except Exception as e:
            logger.error(f"Failed to write jfin reasoning: {e}")

        logger.info(
            f"[JFIN] {group_name} {direction} {primary_score}: "
            f"avg={avg_score:.2f}, threshold={threshold:.2f}, "
            f"criterion1={len(criterion1_candidates)}, criterion2={len(criterion2_candidates)}, "
            f"intersection={len(intersection_candidates)}"
        )
        
        # Apply secondary score filter if provided (for BB Long: FB → BB)
        if secondary_score and intersection_candidates:
            valid_secondary = []
            for c in intersection_candidates:
                score_val = c.get(secondary_score) or c.get(secondary_score.lower(), None)
                if score_val is not None and not (isinstance(score_val, float) and math.isnan(score_val)):
                    valid_secondary.append(c)
            if valid_secondary:
                # Sort by secondary score
                if direction == 'LONG':
                    intersection_candidates = sorted(
                        valid_secondary,
                        key=lambda x: float(x.get(secondary_score, x.get(secondary_score.lower(), 0)) or 0),
                        reverse=True
                    )
                else:
                    intersection_candidates = sorted(
                        valid_secondary,
                        key=lambda x: float(x.get(secondary_score, x.get(secondary_score.lower(), 0)) or 0),
                        reverse=False
                    )
                # Log reasoning for secondary filter
                filter_log = f"\\n[JFIN] {group_name} {direction} {primary_score} -> Secondary Filter {secondary_score}:\\n"
                for c in intersection_candidates:
                    score_val = c.get(secondary_score) or c.get(secondary_score.lower(), 0)
                    filter_log += f"  - {c.get('symbol')}: {secondary_score}={score_val} (Kept)\\n"
                
                try:
                    with open("logs/jfin_reasoning.txt", "a", encoding="utf-8") as f:
                        f.write(filter_log)
                except:
                    pass
                
                logger.info(
                    f"[JFIN] {group_name} {direction}: Applied secondary filter {secondary_score}: "
                    f"{len(intersection_candidates)} candidates"
                )
        
        # Apply company limit (Janall: limit_by_company)
        if self.config.company_limit_enabled:
            intersection_candidates = self._apply_company_limit(
                intersection_candidates, direction, candidates
            )
        
        # Apply selection count limit
        selection_count = max(
            self.config.min_selection,
            int(len(candidates) * self.config.selection_percent)
        )
        
        if direction == 'LONG':
            final_selected = sorted(
                intersection_candidates,
                key=lambda x: float(x.get(primary_score, x.get(primary_score.lower(), 0)) or 0),
                reverse=True
            )[:selection_count]
        else:  # SHORT
            # Apply max_short limit for SHORT
            max_short = self.config.max_short
            final_selected = sorted(
                intersection_candidates,
                key=lambda x: float(x.get(primary_score, x.get(primary_score.lower(), 0)) or 0),
                reverse=False
            )[:min(selection_count, max_short)]
        
        logger.info(
            f"[JFIN] {group_name} {direction} {primary_score}: "
            f"Final selection: {len(final_selected)} stocks"
        )
        
        return final_selected
    
    def _apply_company_limit(
        self,
        selected_candidates: List[Dict[str, Any]],
        direction: str,
        all_candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Apply company limit (Janall: limit_by_company)
        
        Rule: max_per_company = company_total / 1.6 (minimum 1)
        """
        if not selected_candidates:
            return []
        
        # Group by company (CMON)
        company_groups: Dict[str, List[Dict[str, Any]]] = {}
        for c in selected_candidates:
            company = c.get('CMON', c.get('cmon', 'N/A'))
            if company not in company_groups:
                company_groups[company] = []
            company_groups[company].append(c)
        
        # Count total stocks per company in all candidates
        company_totals: Dict[str, int] = {}
        for c in all_candidates:
            company = c.get('CMON', c.get('cmon', 'N/A'))
            company_totals[company] = company_totals.get(company, 0) + 1
        
        # Apply limit per company
        limited_candidates = []
        for company, company_stocks in company_groups.items():
            company_total = company_totals.get(company, len(company_stocks))
            max_allowed = max(1, round(company_total / self.config.company_limit_divisor))
            
            # Sort by score (highest for LONG, lowest for SHORT)
            if direction == 'LONG':
                # Use Final_FB_skor or Final_BB_skor
                score_col = 'Final_FB_skor'
                if not any(c.get(score_col) for c in company_stocks):
                    score_col = 'Final_BB_skor'
                company_stocks_sorted = sorted(
                    company_stocks,
                    key=lambda x: float(x.get(score_col, x.get(score_col.lower(), 0)) or 0),
                    reverse=True
                )
            else:  # SHORT
                # Use Final_SAS_skor or Final_SFS_skor
                score_col = 'Final_SAS_skor'
                if not any(c.get(score_col) for c in company_stocks):
                    score_col = 'Final_SFS_skor'
                company_stocks_sorted = sorted(
                    company_stocks,
                    key=lambda x: float(x.get(score_col, x.get(score_col.lower(), 0)) or 0),
                    reverse=False
                )
            
            limited_candidates.extend(company_stocks_sorted[:max_allowed])
            
            logger.debug(
                f"[JFIN] Company limit {company}: {company_total} total → "
                f"max {max_allowed} allowed → selected {min(len(company_stocks), max_allowed)}"
            )
        
        return limited_candidates
    
    def _select_heldkuponlu_stocks(
        self,
        group_candidates: List[Dict[str, Any]],
        group_name: str
    ) -> Tuple[List[JFINStock], List[JFINStock], List[JFINStock], List[JFINStock]]:
        """
        HELDKUPONLU special logic: CGRUP-based selection
        
        Janall logic:
        - C600, C625, C650: Free (can be 0 or more)
        - Other CGRUPs: At least 1 each
        - Total: heldkuponlu_pair_count pairs per pool
        """
        # TODO: Implement HELDKUPONLU CGRUP-based selection
        # For now, use normal selection logic
        logger.info(f"[JFIN] HELDKUPONLU special logic not yet implemented, using normal selection")
        
        bb_selected = self._select_stocks_janall_logic(
            group_candidates, 'Final_FB_skor', 'Final_BB_skor', 'LONG', group_name
        )
        fb_selected = self._select_stocks_janall_logic(
            group_candidates, 'Final_FB_skor', None, 'LONG', group_name
        )
        
        # Exclude LONG stocks from SHORT selection
        long_symbols = {c.get('symbol', c.get('PREF_IBKR', c.get('PREF IBKR', ''))) for c in bb_selected + fb_selected}
        short_candidates = [
            c for c in group_candidates
            if c.get('symbol', c.get('PREF_IBKR', c.get('PREF IBKR', ''))) not in long_symbols
        ]
        
        sas_selected = self._select_stocks_janall_logic(
            short_candidates, 'Final_SAS_skor', None, 'SHORT', group_name
        )
        sfs_selected = self._select_stocks_janall_logic(
            short_candidates, 'Final_SFS_skor', None, 'SHORT', group_name
        )
        
        # Convert to JFINStock
        bb_stocks = [self._candidate_to_jfin_stock(c, group_name, JFINScoreType.BB_LONG) for c in bb_selected]
        fb_stocks = [self._candidate_to_jfin_stock(c, group_name, JFINScoreType.FB_LONG) for c in fb_selected]
        sas_stocks = [self._candidate_to_jfin_stock(c, group_name, JFINScoreType.SAS_SHORT) for c in sas_selected]
        sfs_stocks = [self._candidate_to_jfin_stock(c, group_name, JFINScoreType.SFS_SHORT) for c in sfs_selected]
        
        return bb_stocks, fb_stocks, sas_stocks, sfs_stocks
    
    def _candidate_to_jfin_stock(
        self,
        candidate: Dict[str, Any],
        group: str,
        score_type: JFINScoreType
    ) -> JFINStock:
        """Convert candidate dict to JFINStock"""
        return JFINStock(
            symbol=candidate.get('symbol', candidate.get('PREF_IBKR', candidate.get('PREF IBKR', ''))),
            group=group,
            cgrup=candidate.get('cgrup', candidate.get('CGRUP')),
            score_type=score_type,
            final_bb_skor=float(candidate.get('Final_BB_skor', candidate.get('final_bb_skor', 0)) or 0),
            final_fb_skor=float(candidate.get('Final_FB_skor', candidate.get('final_fb_skor', 0)) or 0),
            final_sas_skor=float(candidate.get('Final_SAS_skor', candidate.get('final_sas_skor', 0)) or 0),
            final_sfs_skor=float(candidate.get('Final_SFS_skor', candidate.get('final_sfs_skor', 0)) or 0),
            fbtot=float(candidate.get('fbtot', candidate.get('Fbtot', candidate.get('FBTOT', 0))) or 0),
            sfstot=float(candidate.get('sfstot', candidate.get('SFStot', candidate.get('SFSTOT', 0))) or 0),
            gort=float(candidate.get('gort', candidate.get('GORT', 0)) or 0),
            sma63_chg=float(candidate.get('sma63_chg', candidate.get('SMA63_CHG', 0)) or 0),
            maxalw=int(candidate.get('maxalw', candidate.get('MAXALW', 0)) or 0),
            current_position=int(candidate.get('current_position', candidate.get('qty', 0)) or 0),
        )
    
    def _distribute_lots(
        self,
        stocks: List[JFINStock],
        direction: str  # 'long' or 'short'
    ) -> List[JFINStock]:
        """
        Step 2: Alpha-weighted Lot Distribution
        
        Formula:
        - Group Lot = Total Lot Rights × (Group Weight / 100) × Alpha
        - Stock Lot = Group Lot × (Stock Score / Group Total Score)
        """
        if not stocks:
            return stocks
        
        total_rights = (
            self.config.total_long_rights if direction == 'long' 
            else self.config.total_short_rights
        )
        weights = self._group_weights.get(direction, {})
        
        # Group stocks by group
        groups: Dict[str, List[JFINStock]] = {}
        for stock in stocks:
            if stock.group not in groups:
                groups[stock.group] = []
            groups[stock.group].append(stock)
        
        # Distribute lots per group
        for group_name, group_stocks in groups.items():
            weight = weights.get(group_name, 0)
            if weight <= 0:
                continue
            
            # Group lot rights
            group_lot = total_rights * (weight / 100) * self.config.alpha
            
            # Calculate total score for this group
            total_score = sum(abs(self._get_primary_score(s)) for s in group_stocks)
            if total_score == 0:
                # Equal distribution if no scores
                per_stock = group_lot / len(group_stocks)
                for stock in group_stocks:
                    stock.calculated_lot = int(round(per_stock / self.config.lot_rounding) * self.config.lot_rounding)
            else:
                # Score-weighted distribution
                for stock in group_stocks:
                    score_ratio = abs(self._get_primary_score(stock)) / total_score
                    lot = group_lot * score_ratio
                    stock.calculated_lot = int(round(lot / self.config.lot_rounding) * self.config.lot_rounding)
        
        return stocks
    
    def _get_primary_score(self, stock: JFINStock) -> float:
        """Get primary score based on score type"""
        if stock.score_type == JFINScoreType.BB_LONG:
            return stock.final_bb_skor
        elif stock.score_type == JFINScoreType.FB_LONG:
            return stock.final_fb_skor
        elif stock.score_type == JFINScoreType.SAS_SHORT:
            return stock.final_sas_skor
        elif stock.score_type == JFINScoreType.SFS_SHORT:
            return stock.final_sfs_skor
        return 0.0
    
    def _calculate_addable_lots(
        self,
        stocks: List[JFINStock],
        positions: Dict[str, Dict[str, Any]],
        befday_positions: Dict[str, int]
    ) -> List[JFINStock]:
        """
        Step 3: Addable Lot Calculation
        
        Clips calculated_lot to:
        1. MAXALW remaining (maxalw - current_position)
        2. Daily change limit (befday × 2)
        
        ORDER MATTERS: This runs AFTER lot distribution
        """
        for stock in stocks:
            # Get position data
            pos_data = positions.get(stock.symbol, {})
            stock.current_position = int(pos_data.get('qty', pos_data.get('quantity', 0)) or 0)
            stock.befday_qty = befday_positions.get(stock.symbol, 0)
            
            # 1. MAXALW remaining
            maxalw_remaining = stock.maxalw - abs(stock.current_position)
            maxalw_remaining = max(0, maxalw_remaining)
            
            # 2. Daily change limit (BEFDAY × 2)
            if stock.befday_qty != 0:
                daily_limit = abs(stock.befday_qty) * 2
                current_daily_change = abs(stock.current_position - stock.befday_qty)
                daily_remaining = daily_limit - current_daily_change
                daily_remaining = max(0, daily_remaining)
            else:
                # No BEFDAY, use calculated_lot × 2 as limit
                daily_remaining = stock.calculated_lot * 2
            
            # Addable = min(Calculated, MAXALW remaining, Daily remaining)
            stock.addable_lot = min(
                stock.calculated_lot,
                maxalw_remaining,
                daily_remaining
            )
            
            # Round to lot_rounding
            stock.addable_lot = int(stock.addable_lot // self.config.lot_rounding) * self.config.lot_rounding
        
        return stocks
    
    def _apply_percentage_and_exposure(
        self,
        stocks: List[JFINStock],
        max_addable_total: Optional[int],
        direction: str
    ) -> List[JFINStock]:
        """
        Step 4: Apply JFIN Percentage and Exposure Adjustment
        
        1. Apply percentage (25%, 50%, 75%, 100%)
        2. Clip to addable_lot
        3. Apply exposure adjustment if needed
        """
        if not stocks:
            return stocks
        
        # Apply percentage
        for stock in stocks:
            percentage_lot = stock.calculated_lot * (self.config.jfin_percentage / 100)
            
            # Clip to addable_lot
            stock.final_lot = min(int(percentage_lot), stock.addable_lot)
            
            # Round (down for non-100%, normal for 100%)
            if self.config.jfin_percentage == 100:
                stock.final_lot = int(round(stock.final_lot / self.config.lot_rounding) * self.config.lot_rounding)
            else:
                stock.final_lot = int(stock.final_lot // self.config.lot_rounding) * self.config.lot_rounding
        
        # Apply exposure adjustment if max_addable_total is set
        if max_addable_total and max_addable_total > 0:
            current_total = sum(s.final_lot for s in stocks)
            adjusted_max = max_addable_total * (self.config.exposure_percent / 100)
            
            if current_total > adjusted_max and current_total > 0:
                ratio = adjusted_max / current_total
                for stock in stocks:
                    original = stock.final_lot
                    adjusted = int(original * ratio)
                    stock.final_lot = int(adjusted // self.config.lot_rounding) * self.config.lot_rounding
                    stock.final_lot = max(self.config.min_lot_per_order, stock.final_lot)
        
        # Filter out stocks below minimum
        stocks = [s for s in stocks if s.final_lot >= self.config.min_lot_per_order]
        
        return stocks
    
    def _calculate_prices(
        self,
        stocks: List[JFINStock],
        market_data: Dict[str, Dict[str, Any]],
        order_type: JFINOrderType
    ) -> List[JFINStock]:
        """
        Step 5: Calculate Order Prices
        
        - BB: bid + (spread × 0.15)
        - FB: last + 0.01
        - SAS: ask - (spread × 0.15)
        - SFS: last - 0.01
        """
        for stock in stocks:
            md = market_data.get(stock.symbol, {})
            stock.bid = float(md.get('bid', 0) or 0)
            stock.ask = float(md.get('ask', 0) or 0)
            stock.last = float(md.get('last', md.get('price', 0)) or 0)
            
            spread = stock.ask - stock.bid if stock.ask > 0 and stock.bid > 0 else 0
            
            if order_type == JFINOrderType.BB:
                stock.order_price = round(stock.bid + (spread * 0.15), 2)
            elif order_type == JFINOrderType.FB:
                stock.order_price = round(stock.last + 0.01, 2)
            elif order_type == JFINOrderType.SAS:
                stock.order_price = round(stock.ask - (spread * 0.15), 2)
            elif order_type == JFINOrderType.SFS:
                stock.order_price = round(stock.last - 0.01, 2)
        
        return stocks
    
    def _generate_intents(
        self,
        stocks: List[JFINStock],
        score_type: JFINScoreType,
        order_type: JFINOrderType
    ) -> List[JFINIntent]:
        """
        Step 6: Generate Intentions (NOT orders!)
        
        ⚠️ THESE ARE INTENTIONS, NOT ORDERS
        They require user approval before execution.
        """
        intents = []
        
        action = 'BUY' if score_type in [JFINScoreType.BB_LONG, JFINScoreType.FB_LONG] else 'SELL'
        
        for stock in stocks:
            if stock.final_lot < self.config.min_lot_per_order:
                continue
            
            intent = JFINIntent(
                id=f"JFIN_{stock.symbol}_{score_type.value}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
                symbol=stock.symbol,
                group=stock.group,
                cgrup=stock.cgrup,
                score_type=score_type.value,
                order_type=order_type.value,
                action=action,
                qty=stock.final_lot,
                price=stock.order_price,
                calculated_lot=stock.calculated_lot,
                addable_lot=stock.addable_lot,
                percentage_applied=self.config.jfin_percentage,
                exposure_adjusted=stock.final_lot < stock.addable_lot,
                score=self._get_primary_score(stock),
                fbtot=stock.fbtot,
                sfstot=stock.sfstot,
                gort=stock.gort,
                maxalw=stock.maxalw,
                current_position=stock.current_position,
                befday_qty=stock.befday_qty,
                reason_code=f"JFIN_{order_type.value}_{self.config.jfin_percentage}PCT",
                reason_text=f"JFIN {order_type.value} {self.config.jfin_percentage}% - Group: {stock.group}"
            )
            
            intents.append(intent)
        
        return intents


    def get_jfin_state(self) -> Dict[str, Any]:
        """
        Get current JFIN state for all 4 tabs.
        
        Returns:
            Dict with bb_stocks, fb_stocks, sas_stocks, sfs_stocks
        """
        from app.psfalgo.jfin_store import get_jfin_store
        store = get_jfin_store()
        state = store.get_state()
        return state.to_dict()
    
    def get_tab_stocks(self, tab_name: str) -> List[Dict[str, Any]]:
        """
        Get stocks for specific tab.
        
        Args:
            tab_name: 'BB', 'FB', 'SAS', or 'SFS'
        
        Returns:
            List of stock dicts
        """
        from app.psfalgo.jfin_store import get_jfin_store
        store = get_jfin_store()
        stocks = store.get_tab_stocks(tab_name)
        return [stock.to_dict() if hasattr(stock, 'to_dict') else stock for stock in stocks]


# Global instance
_jfin_engine: Optional[JFINEngine] = None


def get_jfin_engine() -> Optional[JFINEngine]:
    """Get global JFINEngine instance"""
    return _jfin_engine


def initialize_jfin_engine(config: Optional[Dict[str, Any]] = None) -> JFINEngine:
    """Initialize global JFINEngine instance"""
    global _jfin_engine
    
    if config:
        # Filter out invalid parameters (like 'enabled' which is not in JFINConfig)
        valid_params = {
            'selection_percent', 'min_selection', 'heldkuponlu_pair_count',
            'long_percent', 'long_multiplier', 'short_percent', 'short_multiplier', 'max_short',
            'company_limit_enabled', 'company_limit_divisor',
            'alpha', 'total_long_rights', 'total_short_rights',
            'jfin_percentage', 'exposure_percent',
            'min_lot_per_order', 'lot_rounding', 'separate_pools'
        }
        filtered_config = {k: v for k, v in config.items() if k in valid_params}
        jfin_config = JFINConfig(**filtered_config)
    else:
        jfin_config = JFINConfig()
    
    _jfin_engine = JFINEngine(config=jfin_config)
    logger.info("[JFIN] Engine initialized globally")
    return _jfin_engine

