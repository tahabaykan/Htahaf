"""
FRONTLAMA ENGINE - Front-Run / Price Improvement Logic

═══════════════════════════════════════════════════════════════════════════════
CORE PHILOSOPHY (ABSOLUTE RULE)
═══════════════════════════════════════════════════════════════════════════════

Sacrifice (fedakârlık) MUST ALWAYS be measured against the BASE PRICE of the order.

NEVER measure sacrifice relative to:
    - current working order
    - previously fronted prices
    - incremental steps

ALWAYS measure relative to:
    "Where would this order be placed if it were sent from scratch?"

This prevents gradual uncontrolled fronting and ensures deterministic risk behavior.

═══════════════════════════════════════════════════════════════════════════════
4-TAG SYSTEM (LU TAXONOMY)
═══════════════════════════════════════════════════════════════════════════════

    MM_DECREASE  → fastest profit taking (🔥 Most aggressive)
    LT_DECREASE  → controlled position reduction (🟢 Aggressive)  
    MM_INCREASE  → cautious new MM risk (🟡 Controlled)
    LT_INCREASE  → extremely conservative new LT risk (🔴 Most strict)

═══════════════════════════════════════════════════════════════════════════════
"""

from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from loguru import logger
import time


class OrderTag(Enum):
    """
    8-Tag Order Classification System
    
    ═══════════════════════════════════════════════════════════════════════════════
    LONG POZİSYONLAR (befday > 0):
    ═══════════════════════════════════════════════════════════════════════════════
    
    LT_LONG_INC = Long-Term Long Increase
                  → BUY emri (pozisyona ekleme)
                  → Yeni risk alıyoruz, EN KATI limitler
                  
    LT_LONG_DEC = Long-Term Long Decrease  
                  → SELL emri (pozisyon azaltma)
                  → Risk azaltıyoruz, AGRESİF frontlama OK
                  
    MM_LONG_INC = Market-Maker Long Increase
                  → BUY emri (MM pozisyona ekleme)
                  → Kontrollü yeni risk
                  
    MM_LONG_DEC = Market-Maker Long Decrease
                  → SELL emri (MM pozisyon azaltma)
                  → KAR ALMA, EN AGRESİF frontlama
    
    ═══════════════════════════════════════════════════════════════════════════════
    SHORT POZİSYONLAR (befday < 0):
    ═══════════════════════════════════════════════════════════════════════════════
    
    LT_SHORT_INC = Long-Term Short Increase
                   → SELL emri (short artırma)
                   → Yeni risk alıyoruz, EN KATI limitler
                   
    LT_SHORT_DEC = Long-Term Short Decrease
                   → BUY emri (short kapatma / cover)
                   → Risk azaltıyoruz, AGRESİF frontlama OK
                   
    MM_SHORT_INC = Market-Maker Short Increase
                   → SELL emri (MM short artırma)
                   → Kontrollü yeni risk
                   
    MM_SHORT_DEC = Market-Maker Short Decrease
                   → BUY emri (MM short kapatma / cover)
                   → KAR ALMA, EN AGRESİF frontlama
    
    ═══════════════════════════════════════════════════════════════════════════════
    """
    # LONG TAGS
    LT_LONG_INC = "LT_LONG_INC"   # BUY emri - yeni LT risk
    LT_LONG_DEC = "LT_LONG_DEC"   # SELL emri - LT pozisyon azaltma
    MM_LONG_INC = "MM_LONG_INC"   # BUY emri - yeni MM risk
    MM_LONG_DEC = "MM_LONG_DEC"   # SELL emri - MM kar alma
    
    # SHORT TAGS
    LT_SHORT_INC = "LT_SHORT_INC"  # SELL emri - yeni LT short risk
    LT_SHORT_DEC = "LT_SHORT_DEC"  # BUY emri - LT short kapatma (cover)
    MM_SHORT_INC = "MM_SHORT_INC"  # SELL emri - yeni MM short risk
    MM_SHORT_DEC = "MM_SHORT_DEC"  # BUY emri - MM short kapatma (cover)
    
    # Backward compatibility aliases (map to 8-tag)
    MM_DECREASE = "MM_DECREASE"   # Generic decrease (will be mapped)
    LT_DECREASE = "LT_DECREASE"   # Generic decrease (will be mapped)
    MM_INCREASE = "MM_INCREASE"   # Generic increase (will be mapped)
    LT_INCREASE = "LT_INCREASE"   # Generic increase (will be mapped)
    
    UNKNOWN = "UNKNOWN"


@dataclass
class FrontlamaLimits:
    """
    Sacrifice limits for each tag category.
    
    BOTH conditions must be met:
        1) sacrificed_cents <= max_cent_limit
        2) sacrifice_ratio <= max_ratio_limit
    """
    max_cent_limit: float      # Maximum sacrifice in cents
    max_ratio_limit: float     # Maximum sacrifice as % of spread


@dataclass
class FrontlamaDecision:
    """Result of frontlama evaluation"""
    allowed: bool                          # Can this order be fronted?
    base_price: float                      # Calculated base price
    front_price: Optional[float]           # Proposed front price (if allowed)
    sacrificed_cents: float                # |base_price - front_price|
    sacrifice_ratio: float                 # sacrificed_cents / spread
    reason: str                            # Human-readable explanation
    tag: OrderTag                          # Order tag category
    exposure_pct: float                    # Current exposure percentage


class FrontlamaEngine:
    """
    FRONTLAMA ENGINE - Deterministic Front-Run Logic
    
    Runs once per minute and evaluates ALL ACTIVE ORDERS
    to decide whether an order may be FRONTED to capture a nearby
    TRUTH TICK fill.
    """
    
    # ═══════════════════════════════════════════════════════════════════════
    # GLOBAL HARD CONSTRAINTS
    # ═══════════════════════════════════════════════════════════════════════
    
    MIN_SPREAD_FOR_FRONTLAMA = 0.04  # If spread < 0.04 → FRONTING IS FORBIDDEN (unless narrow-spread eligible)
    NARROW_SPREAD_THRESHOLD = 0.04   # Spread < 0.04 → only DECREASE tags with special eligibility
    
    # ═══════════════════════════════════════════════════════════════════════
    # BASE LIMITS (Exposure 60-70%) - DOLAR CINSINDEN
    # ═══════════════════════════════════════════════════════════════════════
    #
    # 8 TAG SİSTEMİ LİMİTLERİ:
    #
    # ┌─────────────────────────────────────────────────────────────────────┐
    # │  DECREASE (Risk Azaltma) - Frontlama İSTENİR                       │
    # ├─────────────────────────────────────────────────────────────────────┤
    # │  MM_*_DEC  │ $0.60 │ 50% │ 🔥 EN AGRESİF - Kar kilitleme         │
    # │  LT_*_DEC  │ $0.35 │ 25% │ 🟢 AGRESİF - Pozisyon azaltma         │
    # ├─────────────────────────────────────────────────────────────────────┤
    # │  INCREASE (Yeni Risk) - Frontlama KISITLI                          │
    # ├─────────────────────────────────────────────────────────────────────┤
    # │  LT_*_INC  │ $0.10 │ 10% │ 🟡 KISITLI - Yeni LT risk             │
    # │  MM_*_INC  │ $0.07 │ 7%  │ 🔴 EN KATI - MM yeni risk (LT'den-3%)│
    # └─────────────────────────────────────────────────────────────────────┘
    #
    # NOT: MM INCREASE, LT INCREASE'den %3 DAHA KISITLI
    #      Çünkü MM = kısa vadeli trade, giriş fiyatı çok önemli
    #
    
    BASE_LIMITS = {
        # ═══════════════════════════════════════════════════════════════════
        # DECREASE TAGS - Risk azaltma, frontlama İSTENİR
        # ═══════════════════════════════════════════════════════════════════
        
        # MM DECREASE (Long veya Short fark etmez - kar kilitleme)
        OrderTag.MM_LONG_DEC:  FrontlamaLimits(max_cent_limit=0.60, max_ratio_limit=0.50),  # SELL long = kar al
        OrderTag.MM_SHORT_DEC: FrontlamaLimits(max_cent_limit=0.60, max_ratio_limit=0.50),  # BUY cover = kar al
        OrderTag.MM_DECREASE:  FrontlamaLimits(max_cent_limit=0.60, max_ratio_limit=0.50),  # Generic alias
        
        # LT DECREASE (Long veya Short fark etmez - pozisyon azaltma)
        OrderTag.LT_LONG_DEC:  FrontlamaLimits(max_cent_limit=0.35, max_ratio_limit=0.25),  # SELL long = azalt
        OrderTag.LT_SHORT_DEC: FrontlamaLimits(max_cent_limit=0.35, max_ratio_limit=0.25),  # BUY cover = azalt
        OrderTag.LT_DECREASE:  FrontlamaLimits(max_cent_limit=0.35, max_ratio_limit=0.25),  # Generic alias
        
        # ═══════════════════════════════════════════════════════════════════
        # INCREASE TAGS - Yeni risk, frontlama KISITLI
        # ═══════════════════════════════════════════════════════════════════
        
        # LT INCREASE (Long veya Short fark etmez - yeni LT risk)
        # LT = Uzun vadeli, her cent önemli, frontlama KISITLI
        OrderTag.LT_LONG_INC:  FrontlamaLimits(max_cent_limit=0.10, max_ratio_limit=0.10),  # BUY long = yeni risk
        OrderTag.LT_SHORT_INC: FrontlamaLimits(max_cent_limit=0.10, max_ratio_limit=0.10),  # SELL short = yeni risk
        OrderTag.LT_INCREASE:  FrontlamaLimits(max_cent_limit=0.10, max_ratio_limit=0.10),  # Generic alias
        
        # MM INCREASE (Long veya Short fark etmez - yeni MM risk)
        # MM INCREASE = LT'den %3 DAHA KISITLI (0.10-0.03=0.07)
        # MM yeni pozisyon açmak = kısa vadeli trade, frontlama çok KISITLI
        OrderTag.MM_LONG_INC:  FrontlamaLimits(max_cent_limit=0.07, max_ratio_limit=0.07),  # BUY long = yeni risk
        OrderTag.MM_SHORT_INC: FrontlamaLimits(max_cent_limit=0.07, max_ratio_limit=0.07),  # SELL short = yeni risk
        OrderTag.MM_INCREASE:  FrontlamaLimits(max_cent_limit=0.07, max_ratio_limit=0.07),  # Generic alias
    }
    
    # ═══════════════════════════════════════════════════════════════════════
    # TRUTH TICK VALIDATION
    # ═══════════════════════════════════════════════════════════════════════
    
    FNRA_VALID_SIZES = {100, 200}  # FNRA: ONLY 100 or 200 lot
    NON_FNRA_MIN_SIZE = 15         # Other venues: size >= 15
    
    def __init__(self):
        """Initialize Frontlama Engine"""
        self._last_run_ts: float = 0
        self._run_count: int = 0
        logger.info("[FrontlamaEngine] ✓ Initialized with deterministic sacrifice logic")
    
    # ═══════════════════════════════════════════════════════════════════════
    # PUBLIC API
    # ═══════════════════════════════════════════════════════════════════════
    
    def evaluate_order_for_frontlama(
        self,
        order: Dict[str, Any],
        l1_data: Dict[str, Any],
        truth_last: Optional[float],
        truth_venue: Optional[str],
        truth_size: Optional[float],
        exposure_pct: float
    ) -> FrontlamaDecision:
        """
        Evaluate whether an order can be fronted.
        
        Args:
            order: Active order dict with {symbol, action, price, qty, tag}
            l1_data: Market data with {bid, ask, spread}
            truth_last: Last valid truth tick price
            truth_venue: Venue of the truth tick (FNRA, NYSE, etc.)
            truth_size: Size of the truth tick
            exposure_pct: Current portfolio exposure (0-100+)
            
        Returns:
            FrontlamaDecision with allowed/denied and reasoning
        """
        symbol = order.get('symbol', 'UNKNOWN')
        action = (order.get('action') or order.get('side') or '').upper()  # BUY or SELL
        current_price = order.get('price', 0)
        order_tag_str = order.get('tag') or order.get('strategy_tag') or ''
        
        bid = l1_data.get('bid', 0)
        ask = l1_data.get('ask', 0)
        spread = l1_data.get('spread', 0)
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 1: Classify order tag (with action context for better inference)
        # ─────────────────────────────────────────────────────────────────────
        position_direction = order.get('position_direction')  # LONG or SHORT from befday
        tag = self._classify_order_tag(order_tag_str, action, position_direction)
        
        if tag == OrderTag.UNKNOWN:
            return FrontlamaDecision(
                allowed=False,
                base_price=0,
                front_price=None,
                sacrificed_cents=0,
                sacrifice_ratio=0,
                reason="UNKNOWN_TAG",
                tag=tag,
                exposure_pct=exposure_pct
            )
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 2: Calculate BASE PRICE (the anchor - never changes)
        # ─────────────────────────────────────────────────────────────────────
        base_price = self._calculate_base_price(action, bid, ask, spread)
        
        if base_price <= 0:
            return FrontlamaDecision(
                allowed=False,
                base_price=0,
                front_price=None,
                sacrificed_cents=0,
                sacrifice_ratio=0,
                reason="INVALID_L1_DATA",
                tag=tag,
                exposure_pct=exposure_pct
            )
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 3: SPREAD CHECK (narrow-spread aware)
        # ─────────────────────────────────────────────────────────────────────
        if spread < self.NARROW_SPREAD_THRESHOLD:
            # Narrow spread (<$0.05): Only eligible DECREASE tags allowed
            if not self._is_narrow_spread_eligible(tag, order_tag_str):
                return FrontlamaDecision(
                    allowed=False,
                    base_price=base_price,
                    front_price=None,
                    sacrificed_cents=0,
                    sacrifice_ratio=0,
                    reason=f"NARROW_SPREAD_{spread:.2f}<{self.NARROW_SPREAD_THRESHOLD}_TAG_NOT_ELIGIBLE_{tag.value}",
                    tag=tag,
                    exposure_pct=exposure_pct
                )
            else:
                # ── NARROW SPREAD AGGRESSIVE EXIT ──
                # Spread < $0.04 + eligible DECREASE → go DIRECT to BID/ASK
                # SAFETY CHECK: Don't sell cheap stocks or buy expensive stocks!
                score_ok, score_reason = self._narrow_spread_score_check(symbol, action)
                if not score_ok:
                    return FrontlamaDecision(
                        allowed=False,
                        base_price=base_price,
                        front_price=None,
                        sacrificed_cents=0,
                        sacrifice_ratio=0,
                        reason=f"NARROW_SPREAD_SCORE_BLOCKED_{score_reason}",
                        tag=tag,
                        exposure_pct=exposure_pct
                    )
                
                if action == 'SELL':
                    aggressive_price = round(bid, 2)  # Direct to BID = instant sell fill
                else:
                    aggressive_price = round(ask, 2)  # Direct to ASK = instant buy fill
                
                sacrificed_cents = abs(base_price - aggressive_price)
                sacrifice_ratio = sacrificed_cents / spread if spread > 0 else 0
                
                logger.info(
                    f"[Frontlama] 🏃 NARROW SPREAD EXIT: {symbol} {action} "
                    f"spread=${spread:.3f} < ${self.NARROW_SPREAD_THRESHOLD} — "
                    f"DIRECT TO {'BID' if action == 'SELL' else 'ASK'} "
                    f"${aggressive_price:.2f} [{tag.value}] "
                    f"(sacrifice={sacrificed_cents:.2f}¢, {score_reason})"
                )
                
                return FrontlamaDecision(
                    allowed=True,
                    base_price=base_price,
                    front_price=aggressive_price,
                    sacrificed_cents=sacrificed_cents,
                    sacrifice_ratio=sacrifice_ratio,
                    reason=f"NARROW_SPREAD_AGGRESSIVE_EXIT_{spread:.3f}",
                    tag=tag,
                    exposure_pct=exposure_pct
                )
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 4: Validate truth tick
        # ─────────────────────────────────────────────────────────────────────
        if not self._is_valid_truth_tick(truth_last, truth_venue, truth_size):
            return FrontlamaDecision(
                allowed=False,
                base_price=base_price,
                front_price=None,
                sacrificed_cents=0,
                sacrifice_ratio=0,
                reason="NO_VALID_TRUTH_TICK",
                tag=tag,
                exposure_pct=exposure_pct
            )
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 5: Calculate FRONT PRICE (1-tick from truth)
        # ─────────────────────────────────────────────────────────────────────
        front_price = self._calculate_front_price(action, truth_last)
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 6: Calculate SACRIFICE (always from BASE)
        # ─────────────────────────────────────────────────────────────────────
        sacrificed_cents = abs(base_price - front_price)
        sacrifice_ratio = sacrificed_cents / spread if spread > 0 else 999
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 7: Get adjusted limits based on exposure
        # ─────────────────────────────────────────────────────────────────────
        adjusted_limits, exposure_blocked = self._get_adjusted_limits(tag, exposure_pct)
        
        if exposure_blocked:
            return FrontlamaDecision(
                allowed=False,
                base_price=base_price,
                front_price=front_price,
                sacrificed_cents=sacrificed_cents,
                sacrifice_ratio=sacrifice_ratio,
                reason=f"EXPOSURE_BLOCKS_INCREASE_{exposure_pct:.1f}%",
                tag=tag,
                exposure_pct=exposure_pct
            )
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 8: Check BOTH limits (cent AND ratio)
        # ─────────────────────────────────────────────────────────────────────
        cent_ok = sacrificed_cents <= adjusted_limits.max_cent_limit
        ratio_ok = sacrifice_ratio <= adjusted_limits.max_ratio_limit
        
        if not cent_ok:
            return FrontlamaDecision(
                allowed=False,
                base_price=base_price,
                front_price=front_price,
                sacrificed_cents=sacrificed_cents,
                sacrifice_ratio=sacrifice_ratio,
                reason=f"CENT_LIMIT_EXCEEDED_{sacrificed_cents:.2f}>{adjusted_limits.max_cent_limit:.2f}",
                tag=tag,
                exposure_pct=exposure_pct
            )
        
        if not ratio_ok:
            return FrontlamaDecision(
                allowed=False,
                base_price=base_price,
                front_price=front_price,
                sacrificed_cents=sacrificed_cents,
                sacrifice_ratio=sacrifice_ratio,
                reason=f"RATIO_LIMIT_EXCEEDED_{sacrifice_ratio:.1%}>{adjusted_limits.max_ratio_limit:.1%}",
                tag=tag,
                exposure_pct=exposure_pct
            )
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 9: Sanity check - front price should be "better" for our fill
        # ─────────────────────────────────────────────────────────────────────
        is_improvement = self._is_price_improvement(action, current_price, front_price)
        
        if not is_improvement:
            return FrontlamaDecision(
                allowed=False,
                base_price=base_price,
                front_price=front_price,
                sacrificed_cents=sacrificed_cents,
                sacrifice_ratio=sacrifice_ratio,
                reason="NOT_AN_IMPROVEMENT",
                tag=tag,
                exposure_pct=exposure_pct
            )
        
        # ─────────────────────────────────────────────────────────────────────
        # ALL CHECKS PASSED → FRONTLAMA ALLOWED
        # ─────────────────────────────────────────────────────────────────────
        logger.info(
            f"[Frontlama] ✓ {symbol} {action} ALLOWED: "
            f"base=${base_price:.2f} → front=${front_price:.2f} "
            f"(sacrifice={sacrificed_cents:.2f}¢ = {sacrifice_ratio:.1%} of spread) "
            f"[{tag.value}] [exp={exposure_pct:.1f}%]"
        )
        
        return FrontlamaDecision(
            allowed=True,
            base_price=base_price,
            front_price=front_price,
            sacrificed_cents=sacrificed_cents,
            sacrifice_ratio=sacrifice_ratio,
            reason="FRONTLAMA_APPROVED",
            tag=tag,
            exposure_pct=exposure_pct
        )
    
    def evaluate_with_multi_ticks(
        self,
        order: Dict[str, Any],
        l1_data: Dict[str, Any],
        truth_ticks: list,
        exposure_pct: float
    ) -> FrontlamaDecision:
        """
        Evaluate frontlama using LAST 5 TRUTH TICKS.
        
        For each tick, calculates front_price and checks sacrifice limits
        (which are TAG-SPECIFIC: MM_DEC=$0.60, MM_INC=$0.07, etc.).
        
        Among ticks that PASS all checks, picks the MOST RECENT one
        (newest timestamp = closest to current market context).
        
        If no ticks pass, returns the denial reason from the most recent tick.
        
        Args:
            order: Active order dict with {symbol, action, price, qty, tag}
            l1_data: Market data with {bid, ask, spread}
            truth_ticks: List of dicts, newest first: [{price, venue, size, ts}, ...]
            exposure_pct: Current portfolio exposure (0-100+)
        """
        symbol = order.get('symbol', 'UNKNOWN')
        action = (order.get('action') or order.get('side') or '').upper()
        current_price = order.get('price', 0)
        order_tag_str = order.get('tag') or order.get('strategy_tag') or ''
        
        bid = l1_data.get('bid', 0)
        ask = l1_data.get('ask', 0)
        spread = l1_data.get('spread', 0)
        
        # ── STEP 1: Tag classification (same for all ticks) ──
        position_direction = order.get('position_direction')
        tag = self._classify_order_tag(order_tag_str, action, position_direction)
        
        if tag == OrderTag.UNKNOWN:
            return FrontlamaDecision(
                allowed=False, base_price=0, front_price=None,
                sacrificed_cents=0, sacrifice_ratio=0,
                reason="UNKNOWN_TAG", tag=tag, exposure_pct=exposure_pct
            )
        
        # ── STEP 2: Base price (same for all ticks) ──
        base_price = self._calculate_base_price(action, bid, ask, spread)
        if base_price <= 0:
            return FrontlamaDecision(
                allowed=False, base_price=0, front_price=None,
                sacrificed_cents=0, sacrifice_ratio=0,
                reason="INVALID_L1_DATA", tag=tag, exposure_pct=exposure_pct
            )
        
        # ── STEP 3: Spread check (narrow-spread aware) ──
        if spread < self.NARROW_SPREAD_THRESHOLD:
            if not self._is_narrow_spread_eligible(tag, order_tag_str):
                return FrontlamaDecision(
                    allowed=False, base_price=base_price, front_price=None,
                    sacrificed_cents=0, sacrifice_ratio=0,
                    reason=f"NARROW_SPREAD_{spread:.2f}<{self.NARROW_SPREAD_THRESHOLD}_NOT_ELIGIBLE_{tag.value}",
                    tag=tag, exposure_pct=exposure_pct
                )
            else:
                # ── NARROW SPREAD AGGRESSIVE EXIT (multi-tick path) ──
                score_ok, score_reason = self._narrow_spread_score_check(symbol, action)
                if not score_ok:
                    return FrontlamaDecision(
                        allowed=False, base_price=base_price, front_price=None,
                        sacrificed_cents=0, sacrifice_ratio=0,
                        reason=f"NARROW_SPREAD_SCORE_BLOCKED_{score_reason}",
                        tag=tag, exposure_pct=exposure_pct
                    )
                
                if action == 'SELL':
                    aggressive_price = round(bid, 2)
                else:
                    aggressive_price = round(ask, 2)
                
                sacrificed_cents = abs(base_price - aggressive_price)
                sacrifice_ratio = sacrificed_cents / spread if spread > 0 else 0
                
                logger.info(
                    f"[Frontlama] 🏃 NARROW SPREAD EXIT (multi-tick): {symbol} {action} "
                    f"spread=${spread:.3f} — DIRECT TO {'BID' if action == 'SELL' else 'ASK'} "
                    f"${aggressive_price:.2f} [{tag.value}] "
                    f"(sacrifice={sacrificed_cents:.2f}¢, {score_reason})"
                )
                
                return FrontlamaDecision(
                    allowed=True, base_price=base_price, front_price=aggressive_price,
                    sacrificed_cents=sacrificed_cents, sacrifice_ratio=sacrifice_ratio,
                    reason=f"NARROW_SPREAD_AGGRESSIVE_EXIT_{spread:.3f}",
                    tag=tag, exposure_pct=exposure_pct
                )
        
        # ── STEP 4: Exposure limits (same for all ticks) ──
        adjusted_limits, exposure_blocked = self._get_adjusted_limits(tag, exposure_pct)
        if exposure_blocked:
            return FrontlamaDecision(
                allowed=False, base_price=base_price, front_price=None,
                sacrificed_cents=0, sacrifice_ratio=0,
                reason=f"EXPOSURE_BLOCKS_INCREASE_{exposure_pct:.1f}%",
                tag=tag, exposure_pct=exposure_pct
            )
        
        # ── STEP 5: No ticks at all? ──
        if not truth_ticks:
            return FrontlamaDecision(
                allowed=False, base_price=base_price, front_price=None,
                sacrificed_cents=0, sacrifice_ratio=0,
                reason="NO_VALID_TRUTH_TICK",
                tag=tag, exposure_pct=exposure_pct
            )
        
        # ── STEP 6: Evaluate each tick ──
        # truth_ticks is NEWEST FIRST — iterate in order, first pass wins
        best_decision = None
        last_denial = None
        
        for tick in truth_ticks:
            t_price = tick.get('price', 0)
            t_venue = tick.get('venue', '')
            t_size = tick.get('size', 0)
            
            # Validate truth tick (FNRA rules etc.)
            if not self._is_valid_truth_tick(t_price, t_venue, t_size):
                if last_denial is None:
                    last_denial = FrontlamaDecision(
                        allowed=False, base_price=base_price, front_price=None,
                        sacrificed_cents=0, sacrifice_ratio=0,
                        reason=f"INVALID_TRUTH_TICK_{t_price:.2f}@{t_venue}",
                        tag=tag, exposure_pct=exposure_pct
                    )
                continue
            
            # Calculate front price for this tick
            front_price = self._calculate_front_price(action, t_price)
            
            # Calculate sacrifice (always from BASE)
            sacrificed_cents = abs(base_price - front_price)
            sacrifice_ratio = sacrificed_cents / spread if spread > 0 else 999
            
            # Check limits (TAG-SPECIFIC!)
            cent_ok = sacrificed_cents <= adjusted_limits.max_cent_limit
            ratio_ok = sacrifice_ratio <= adjusted_limits.max_ratio_limit
            
            if not cent_ok:
                last_denial = FrontlamaDecision(
                    allowed=False, base_price=base_price, front_price=front_price,
                    sacrificed_cents=sacrificed_cents, sacrifice_ratio=sacrifice_ratio,
                    reason=f"CENT_LIMIT_{sacrificed_cents:.2f}>{adjusted_limits.max_cent_limit:.2f}_tick@{t_price:.2f}",
                    tag=tag, exposure_pct=exposure_pct
                )
                continue
            
            if not ratio_ok:
                last_denial = FrontlamaDecision(
                    allowed=False, base_price=base_price, front_price=front_price,
                    sacrificed_cents=sacrificed_cents, sacrifice_ratio=sacrifice_ratio,
                    reason=f"RATIO_LIMIT_{sacrifice_ratio:.1%}>{adjusted_limits.max_ratio_limit:.1%}_tick@{t_price:.2f}",
                    tag=tag, exposure_pct=exposure_pct
                )
                continue
            
            # Check improvement
            if not self._is_price_improvement(action, current_price, front_price):
                last_denial = FrontlamaDecision(
                    allowed=False, base_price=base_price, front_price=front_price,
                    sacrificed_cents=sacrificed_cents, sacrifice_ratio=sacrifice_ratio,
                    reason=f"NOT_IMPROVEMENT_tick@{t_price:.2f}",
                    tag=tag, exposure_pct=exposure_pct
                )
                continue
            
            # ✅ THIS TICK PASSED — it's the newest passing tick, USE IT
            logger.info(
                f"[Frontlama] ✓ {symbol} {action} APPROVED (multi-tick): "
                f"base=${base_price:.2f} → front=${front_price:.2f} "
                f"(sacrifice={sacrificed_cents:.2f}¢ = {sacrifice_ratio:.1%} of spread) "
                f"[{tag.value}] [exp={exposure_pct:.1f}%] "
                f"truth_tick=${t_price:.2f}@{t_venue}"
            )
            
            best_decision = FrontlamaDecision(
                allowed=True, base_price=base_price, front_price=front_price,
                sacrificed_cents=sacrificed_cents, sacrifice_ratio=sacrifice_ratio,
                reason=f"APPROVED_tick@{t_price:.2f}",
                tag=tag, exposure_pct=exposure_pct
            )
            break  # Newest passing tick wins
        
        if best_decision:
            return best_decision
        
        # None passed — return last denial reason
        if last_denial:
            return last_denial
        
        return FrontlamaDecision(
            allowed=False, base_price=base_price, front_price=None,
            sacrificed_cents=0, sacrifice_ratio=0,
            reason="NO_VALID_TRUTH_TICK",
            tag=tag, exposure_pct=exposure_pct
        )
    
    # ═══════════════════════════════════════════════════════════════════════
    # BASE PRICE CALCULATION
    # ═══════════════════════════════════════════════════════════════════════
    
    def _calculate_base_price(
        self, 
        action: str, 
        bid: float, 
        ask: float, 
        spread: float
    ) -> float:
        """
        Calculate the BASE PRICE - where the order WOULD be placed from scratch.
        
        For SELL orders:
            base_price = ask - (spread × 0.15)
            
        For BUY orders:
            base_price = bid + (spread × 0.15)
            
        This is the PASSIVE, DISCIPLINED, IDEAL starting price.
        """
        if bid <= 0 or ask <= 0:
            return 0
        
        if action == 'SELL':
            base_price = ask - (spread * 0.15)
        else:  # BUY
            base_price = bid + (spread * 0.15)
        
        return round(base_price, 2)
    
    # ═══════════════════════════════════════════════════════════════════════
    # FRONT PRICE CALCULATION
    # ═══════════════════════════════════════════════════════════════════════
    
    def _calculate_front_price(self, action: str, truth_last: float) -> float:
        """
        Calculate the FRONT PRICE - 1-tick improvement from truth tick.
        
        SELL → front_price = truth_last - 0.01 (go below to get filled)
        BUY  → front_price = truth_last + 0.01 (go above to get filled)
        
        This is the AGGRESSIVE, FRONTING price.
        """
        if action == 'SELL':
            return round(truth_last - 0.01, 2)
        else:  # BUY
            return round(truth_last + 0.01, 2)
    
    # ═══════════════════════════════════════════════════════════════════════
    # TRUTH TICK VALIDATION
    # ═══════════════════════════════════════════════════════════════════════
    
    def _is_valid_truth_tick(
        self, 
        truth_last: Optional[float],
        truth_venue: Optional[str],
        truth_size: Optional[float]
    ) -> bool:
        """
        Validate that we have a REAL truth tick, not a fake/manipulative print.
        
        FNRA: size MUST be exactly 100 or 200
        Other venues (NYSE, ARCA, etc.): size >= 15
        
        Returns True if valid, False otherwise.
        """
        if truth_last is None or truth_last <= 0:
            return False
        
        if truth_size is None or truth_size <= 0:
            return False
        
        venue = (truth_venue or '').upper()
        
        # FNRA strict rule: ONLY 100 or 200
        if venue in ['FNRA', 'ADFN', 'FINRA', 'OTC', 'DARK']:
            return int(truth_size) in self.FNRA_VALID_SIZES
        
        # Other venues: >= 15
        return truth_size >= self.NON_FNRA_MIN_SIZE
    
    # ═══════════════════════════════════════════════════════════════════════
    # ORDER TAG CLASSIFICATION - 8 TAG SYSTEM
    # ═══════════════════════════════════════════════════════════════════════
    
    def _classify_order_tag(
        self, 
        tag_str: str, 
        order_action: str = None,
        position_direction: str = None
    ) -> OrderTag:
        """
        Classify order tag into 8-TAG taxonomy.
        
        8 TAG SİSTEMİ:
        ═══════════════════════════════════════════════════════════════════════
        
        LONG POZİSYONLAR (befday > 0):
        ───────────────────────────────────────────────────────────────────────
        LT_LONG_INC  │ BUY emri  │ Long pozisyona ekleme
        LT_LONG_DEC  │ SELL emri │ Long pozisyon azaltma
        MM_LONG_INC  │ BUY emri  │ MM long pozisyona ekleme
        MM_LONG_DEC  │ SELL emri │ MM long pozisyon azaltma (kar alma)
        
        SHORT POZİSYONLAR (befday < 0):
        ───────────────────────────────────────────────────────────────────────
        LT_SHORT_INC │ SELL emri │ Short pozisyon artırma
        LT_SHORT_DEC │ BUY emri  │ Short pozisyon kapatma (cover)
        MM_SHORT_INC │ SELL emri │ MM short pozisyon artırma
        MM_SHORT_DEC │ BUY emri  │ MM short pozisyon kapatma (kar alma)
        
        ═══════════════════════════════════════════════════════════════════════
        
        Args:
            tag_str: Order tag string (e.g., "LT_LONG_DEC", "MM_CHURN_INCREASE")
            order_action: "BUY" or "SELL" (helps determine direction)
            position_direction: "LONG" or "SHORT" (from befday sign)
        """
        tag_upper = tag_str.upper()
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 1: Check for explicit 8-tag format first
        # ─────────────────────────────────────────────────────────────────────
        if 'LT_LONG_INC' in tag_upper:
            return OrderTag.LT_LONG_INC
        if 'LT_LONG_DEC' in tag_upper:
            return OrderTag.LT_LONG_DEC
        if 'LT_SHORT_INC' in tag_upper:
            return OrderTag.LT_SHORT_INC
        if 'LT_SHORT_DEC' in tag_upper:
            return OrderTag.LT_SHORT_DEC
        if 'MM_LONG_INC' in tag_upper:
            return OrderTag.MM_LONG_INC
        if 'MM_LONG_DEC' in tag_upper:
            return OrderTag.MM_LONG_DEC
        if 'MM_SHORT_INC' in tag_upper:
            return OrderTag.MM_SHORT_INC
        if 'MM_SHORT_DEC' in tag_upper:
            return OrderTag.MM_SHORT_DEC
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 2: Parse legacy tag format
        # ─────────────────────────────────────────────────────────────────────
        
        # Determine LT vs MM
        is_lt = 'LT' in tag_upper or 'TRIM' in tag_upper
        is_mm = 'MM' in tag_upper or 'CHURN' in tag_upper
        
        # Determine INC vs DEC (INC catches INCREASE too since 'INC' in 'INCREASE')
        is_increase = 'INC' in tag_upper
        is_decrease = 'DEC' in tag_upper
        
        # Determine LONG vs SHORT (from tag or context)
        is_long = 'LONG' in tag_upper
        is_short = 'SHORT' in tag_upper
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 3: REV order logic
        # ─────────────────────────────────────────────────────────────────────
        # Legacy REV tags without MM/LT and INC/DEC in explicit 8-tag format
        # REV after INC fill → trying to DEC (take profit)
        # REV after DEC fill → trying to INC (reload)
        # NOTE: New REV tags (REV_MM_LONG_DEC) are caught by Step 1 above.
        # This Step 3 only fires for legacy tags like REV_IBKRPED_LONG_TP.
        if 'REV' in tag_upper:
            if is_increase and not is_decrease:
                is_decrease = True
                is_increase = False
            elif is_decrease and not is_increase:
                is_increase = True
                is_decrease = False
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 4: Infer direction from order_action if not in tag
        # ─────────────────────────────────────────────────────────────────────
        if not is_long and not is_short:
            # Use position_direction if provided
            if position_direction:
                is_long = position_direction.upper() == 'LONG'
                is_short = position_direction.upper() == 'SHORT'
            # Otherwise infer from order_action + increase/decrease
            elif order_action:
                action = order_action.upper()
                if is_increase:
                    # INCREASE + BUY = Long position
                    # INCREASE + SELL = Short position
                    is_long = (action == 'BUY')
                    is_short = (action == 'SELL')
                elif is_decrease:
                    # DECREASE + SELL = Long position (selling long)
                    # DECREASE + BUY = Short position (covering short)
                    is_long = (action == 'SELL')
                    is_short = (action == 'BUY')
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 5: Apply defaults
        # ─────────────────────────────────────────────────────────────────────
        if not is_lt and not is_mm:
            is_lt = True  # Default to LT (more conservative)
        
        if not is_increase and not is_decrease:
            is_decrease = True  # Default to DECREASE (safer limits)
        
        if not is_long and not is_short:
            is_long = True  # Default to LONG
        
        # ─────────────────────────────────────────────────────────────────────
        # STEP 6: Map to 8-tag
        # ─────────────────────────────────────────────────────────────────────
        if is_lt and is_long and is_increase:
            return OrderTag.LT_LONG_INC
        if is_lt and is_long and is_decrease:
            return OrderTag.LT_LONG_DEC
        if is_lt and is_short and is_increase:
            return OrderTag.LT_SHORT_INC
        if is_lt and is_short and is_decrease:
            return OrderTag.LT_SHORT_DEC
        if is_mm and is_long and is_increase:
            return OrderTag.MM_LONG_INC
        if is_mm and is_long and is_decrease:
            return OrderTag.MM_LONG_DEC
        if is_mm and is_short and is_increase:
            return OrderTag.MM_SHORT_INC
        if is_mm and is_short and is_decrease:
            return OrderTag.MM_SHORT_DEC
        
        return OrderTag.UNKNOWN
    
    def _is_decrease_tag(self, tag: OrderTag) -> bool:
        """Check if tag is a DECREASE (risk-reducing) tag"""
        return tag in [
            OrderTag.LT_LONG_DEC, OrderTag.LT_SHORT_DEC,
            OrderTag.MM_LONG_DEC, OrderTag.MM_SHORT_DEC,
            OrderTag.LT_DECREASE, OrderTag.MM_DECREASE
        ]
    
    def _is_increase_tag(self, tag: OrderTag) -> bool:
        """Check if tag is an INCREASE (risk-adding) tag"""
        return tag in [
            OrderTag.LT_LONG_INC, OrderTag.LT_SHORT_INC,
            OrderTag.MM_LONG_INC, OrderTag.MM_SHORT_INC,
            OrderTag.LT_INCREASE, OrderTag.MM_INCREASE
        ]
    
    def _is_narrow_spread_eligible(self, tag: OrderTag, raw_tag_str: str = '') -> bool:
        """
        Check if this tag is eligible for frontlama when spread < $0.05 (narrow).
        
        NARROW SPREAD RULES:
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        ✅ KB (Karbotu) DECREASE     → Always eligible (fast exit)
        ✅ MM DECREASE               → Always eligible (profit taking)
        ✅ LT_TRIM Stage 2/3/4       → Eligible (advanced stages)
        ❌ LT_TRIM Stage 1           → NEVER (first stage = conservative)
        ❌ All INCREASE tags         → NEVER (no new risk on narrow spread)
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        
        When eligible and spread < $0.05: Aggressive pricing allowed
        (direct to BID for SELL, ASK for BUY = instant fill)
        """
        # RULE 1: INCREASE tags → NEVER eligible on narrow spread
        if self._is_increase_tag(tag):
            return False
        
        # RULE 2: Must be a DECREASE tag
        if not self._is_decrease_tag(tag):
            return False
        
        raw = (raw_tag_str or '').upper()
        
        # RULE 3: KB (Karbotu) DECREASE → always eligible
        if 'KB' in raw or 'KARBOTU' in raw or 'HEAVY' in raw:
            return True
        
        # RULE 4: MM DECREASE → always eligible
        if tag in (OrderTag.MM_LONG_DEC, OrderTag.MM_SHORT_DEC, OrderTag.MM_DECREASE):
            return True
        
        # RULE 5: LT_TRIM with stage info
        if 'TRIM' in raw:
            # Stage 1 → BLOCKED (conservative first stage)
            if '_S1' in raw:
                return False
            # Stage 2, 3, 4 → ELIGIBLE (aggressive exit)
            if '_S2' in raw or '_S3' in raw or '_S4' in raw:
                return True
            # No stage info → default BLOCKED (conservative)
            return False
        
        # RULE 6: Generic LT DECREASE without TRIM → eligible
        # (e.g., LT_LONG_DEC from other engines)
        if tag in (OrderTag.LT_LONG_DEC, OrderTag.LT_SHORT_DEC, OrderTag.LT_DECREASE):
            return True
        
        return False
    
    # Narrow spread score safety thresholds
    NARROW_SPREAD_MIN_UCUZLUK_FOR_SELL = 0.05   # bid_buy_ucuzluk >= +0.05 to SELL at BID
    NARROW_SPREAD_MAX_PAHALILIK_FOR_BUY = -0.05  # ask_sell_pahalilik <= -0.05 to BUY at ASK
    
    def _narrow_spread_score_check(self, symbol: str, action: str) -> tuple:
        """
        Safety check for narrow spread aggressive exit.
        
        Prevents:
        - Selling cheap stocks at BID (would be selling at a loss)
        - Buying expensive stocks at ASK (would be buying overpriced)
        
        SELL at BID: bid_buy_ucuzluk >= +0.05 required
            (stock is NOT cheap → safe to sell aggressively)
        
        BUY at ASK: ask_sell_pahalilik <= -0.05 required
            (stock is NOT expensive → safe to buy aggressively)
        
        Returns: (ok: bool, reason: str)
        """
        try:
            from app.core.data_fabric import get_data_fabric
            fabric = get_data_fabric()
            if not fabric:
                return False, "NO_DATA_FABRIC"
            
            snap = fabric.get_fast_snapshot(symbol)
            if not snap or not snap.get('_has_derived'):
                return False, "NO_DERIVED_DATA"
            
            if action == 'SELL':
                # SELL at BID: check bid_buy_ucuzluk >= +0.05
                ucuzluk = snap.get('bid_buy_ucuzluk') or snap.get('Bid_buy_ucuzluk_skoru')
                if ucuzluk is None:
                    return False, "NO_UCUZLUK_SCORE"
                ucuzluk = float(ucuzluk)
                if ucuzluk < self.NARROW_SPREAD_MIN_UCUZLUK_FOR_SELL:
                    return False, (
                        f"UCUZLUK_TOO_LOW_{ucuzluk:.3f}"
                        f"<{self.NARROW_SPREAD_MIN_UCUZLUK_FOR_SELL}"
                    )
                return True, f"ucuzluk={ucuzluk:.3f}>=+0.05_OK"
            
            else:  # BUY
                # BUY at ASK: check ask_sell_pahalilik <= -0.05
                pahalilik = snap.get('ask_sell_pahalilik') or snap.get('Ask_sell_pahalilik_skoru')
                if pahalilik is None:
                    return False, "NO_PAHALILIK_SCORE"
                pahalilik = float(pahalilik)
                if pahalilik > self.NARROW_SPREAD_MAX_PAHALILIK_FOR_BUY:
                    return False, (
                        f"PAHALILIK_TOO_HIGH_{pahalilik:.3f}"
                        f">{self.NARROW_SPREAD_MAX_PAHALILIK_FOR_BUY}"
                    )
                return True, f"pahalilik={pahalilik:.3f}<=-0.05_OK"
        
        except Exception as e:
            logger.debug(f"[Frontlama] Narrow spread score check error: {e}")
            return False, f"SCORE_CHECK_ERROR_{e}"
    # ═══════════════════════════════════════════════════════════════════════
    # EXPOSURE-BASED LIMIT ADJUSTMENTS
    # ═══════════════════════════════════════════════════════════════════════
    
    def _get_adjusted_limits(
        self, 
        tag: OrderTag, 
        exposure_pct: float
    ) -> Tuple[FrontlamaLimits, bool]:
        """
        Get adjusted limits based on current exposure.
        
        CENT LIMITS NEVER CHANGE.
        RATIO LIMITS are adjusted as follows:
        
        Exposure < 60%:     +5% to ratio (more lenient)
        Exposure 60-70%:    No change (base values)
        Exposure 70-80%:    -5% to ratio (tighter)
        Exposure 80-90%:    -8% to ratio (much tighter)
        Exposure 90-95%:    INCREASE: FORBIDDEN, DECREASE: +3%
        Exposure 95-100%+:  INCREASE: FORBIDDEN, DECREASE: +5%
        
        Returns:
            (adjusted_limits, is_blocked_by_exposure)
        """
        base = self.BASE_LIMITS.get(tag, self.BASE_LIMITS[OrderTag.LT_LONG_INC])
        is_increase = self._is_increase_tag(tag)
        
        # ─────────────────────────────────────────────────────────────────────
        # EXPOSURE 95-100%+ (CRISIS MODE)
        # ─────────────────────────────────────────────────────────────────────
        if exposure_pct >= 95:
            if is_increase:
                # INCREASE orders: STRICTLY FORBIDDEN
                return base, True
            else:
                # DECREASE orders: +5% ratio allowance
                return FrontlamaLimits(
                    max_cent_limit=base.max_cent_limit,
                    max_ratio_limit=base.max_ratio_limit + 0.05
                ), False
        
        # ─────────────────────────────────────────────────────────────────────
        # EXPOSURE 90-95% (VERY HIGH RISK)
        # ─────────────────────────────────────────────────────────────────────
        if exposure_pct >= 90:
            if is_increase:
                # INCREASE orders: FRONTING FORBIDDEN
                return base, True
            else:
                # DECREASE orders: +3% ratio allowance
                return FrontlamaLimits(
                    max_cent_limit=base.max_cent_limit,
                    max_ratio_limit=base.max_ratio_limit + 0.03
                ), False
        
        # ─────────────────────────────────────────────────────────────────────
        # EXPOSURE 80-90% (HIGH RISK)
        # ─────────────────────────────────────────────────────────────────────
        if exposure_pct >= 80:
            return FrontlamaLimits(
                max_cent_limit=base.max_cent_limit,
                max_ratio_limit=base.max_ratio_limit - 0.08
            ), False
        
        # ─────────────────────────────────────────────────────────────────────
        # EXPOSURE 70-80% (CAUTIOUS)
        # ─────────────────────────────────────────────────────────────────────
        if exposure_pct >= 70:
            return FrontlamaLimits(
                max_cent_limit=base.max_cent_limit,
                max_ratio_limit=base.max_ratio_limit - 0.05
            ), False
        
        # ─────────────────────────────────────────────────────────────────────
        # EXPOSURE 60-70% (NEUTRAL - BASE VALUES)
        # ─────────────────────────────────────────────────────────────────────
        if exposure_pct >= 60:
            return base, False
        
        # ─────────────────────────────────────────────────────────────────────
        # EXPOSURE < 60% (OPPORTUNISTIC)
        # ─────────────────────────────────────────────────────────────────────
        return FrontlamaLimits(
            max_cent_limit=base.max_cent_limit,
            max_ratio_limit=base.max_ratio_limit + 0.05
        ), False
    
    # ═══════════════════════════════════════════════════════════════════════
    # PRICE IMPROVEMENT CHECK
    # ═══════════════════════════════════════════════════════════════════════
    
    def _is_price_improvement(
        self, 
        action: str, 
        current_price: float, 
        front_price: float
    ) -> bool:
        """
        Check if front_price is actually an improvement for getting filled.
        
        For SELL: front_price should be LOWER (more aggressive)
        For BUY: front_price should be HIGHER (more aggressive)
        """
        if action == 'SELL':
            # For SELL, lower price = more aggressive = better fill chance
            return front_price < current_price
        else:
            # For BUY, higher price = more aggressive = better fill chance
            return front_price > current_price
    
    # ═══════════════════════════════════════════════════════════════════════
    # UTILITY METHODS
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_limits_summary(self, exposure_pct: float) -> Dict[str, Dict[str, Any]]:
        """
        Get current limits for all 8 tags given exposure level.
        Useful for UI/debugging.
        
        Returns a summary with all 8 tags showing:
        - max_cent: Cent limit (NEVER changes with exposure)
        - max_ratio_pct: Ratio limit as percentage (ADJUSTS with exposure)
        - blocked: Whether this tag is blocked at current exposure
        - action: The broker action (BUY or SELL)
        - description: Human-readable description
        """
        summary = {}
        
        # 8-TAG definitions with descriptions
        tag_definitions = [
            # LONG DECREASE tags (selling long positions)
            (OrderTag.MM_LONG_DEC, "SELL", "MM Long Kar Alma - EN AGRESİF frontlama"),
            (OrderTag.LT_LONG_DEC, "SELL", "LT Long Azaltma - AGRESİF frontlama OK"),
            
            # SHORT DECREASE tags (covering short positions)
            (OrderTag.MM_SHORT_DEC, "BUY", "MM Short Cover - EN AGRESİF frontlama"),
            (OrderTag.LT_SHORT_DEC, "BUY", "LT Short Cover - AGRESİF frontlama OK"),
            
            # LONG INCREASE tags (buying long positions)
            (OrderTag.LT_LONG_INC, "BUY", "LT Long Ekleme - KISITLI frontlama (0.10$, 10%)"),
            (OrderTag.MM_LONG_INC, "BUY", "MM Long Ekleme - EN KATI limit (0.07$, 7%)"),
            
            # SHORT INCREASE tags (selling short positions)
            (OrderTag.LT_SHORT_INC, "SELL", "LT Short Artırma - KISITLI frontlama (0.10$, 10%)"),
            (OrderTag.MM_SHORT_INC, "SELL", "MM Short Artırma - EN KATI limit (0.07$, 7%)"),
        ]
        
        for tag, action, description in tag_definitions:
            limits, blocked = self._get_adjusted_limits(tag, exposure_pct)
            summary[tag.value] = {
                'max_cent': limits.max_cent_limit,
                'max_ratio_pct': limits.max_ratio_limit * 100,
                'blocked': blocked,
                'action': action,
                'description': description
            }
        
        return summary


# ═══════════════════════════════════════════════════════════════════════════
# GLOBAL INSTANCE
# ═══════════════════════════════════════════════════════════════════════════

_frontlama_engine: Optional[FrontlamaEngine] = None


def get_frontlama_engine() -> FrontlamaEngine:
    """Get or create singleton FrontlamaEngine instance"""
    global _frontlama_engine
    if _frontlama_engine is None:
        _frontlama_engine = FrontlamaEngine()
    return _frontlama_engine

