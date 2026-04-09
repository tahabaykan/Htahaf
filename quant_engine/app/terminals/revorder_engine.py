"""
REV Order Engine - Professional Implementation

Implements the core REV logic:
1. INCREASE Fills (POS↑): Take Profit (minimum $0.05 / KAR AL)
2. DECREASE Fills (POS↓): Reload, source-specific:
   - LT/KB/PA/AN pos decrease → minimum $0.08
   - MM pos decrease → minimum $0.13
3. ALL REV orders are HIDDEN.
4. 2-Phase pricing: L1 first (max profit), then OrderBook fallback.

PRICING RULES (2-PHASE):
  PHASE 1 (Easy Path - Max Profit):
    - SELL REV: ask - (spread * 0.15)  [hidden, maksimum kâr]
    - BUY REV:  bid + (spread * 0.15)  [hidden, maksimum iskonto]
    - Floor check: computed price must meet min threshold vs fill_price

  PHASE 2 (Orderbook Fallback - when L1 spread too tight):
    - Scan orderbook levels for first level meeting threshold
    - Place $0.01 in front (fixed front-run)

TAG FORMAT (v3):
- REV_{TYPE}_{SOURCE}_{ACTION}
- TYPE: TP (Take Profit) or RL (Reload)
- SOURCE: LT, MM, KB (Karbotu), PA (Patadd), AN (Addnewpos)
- ACTION: BUY or SELL (what the REV order does)
- Examples:
    REV_TP_LT_SELL  (long increase fill -> sell take profit)
    REV_RL_MM_BUY   (MM long decrease fill -> buy reload)
    REV_TP_MM_BUY   (short increase fill -> buy take profit)
    REV_RL_KB_SELL  (karbotu short decrease fill -> sell reload)

NEWCLMM EXCLUSION:
- Fills with NEWC engine tag (MM_NEWC_*) are EXCLUDED from REV processing.
- NEWCLMM has its own truth-tick-based profit-taking mechanism that
  frontruns ticks for quick profit (min 7c). REV would create duplicate
  exit orders and conflict with NEWCLMM's internal TP tracking.
"""
from typing import Dict, Any, Optional, Tuple
from loguru import logger
import json

from app.terminals.orderbook_fetcher import OrderBookFetcher
from app.terminals.revorder_config import load_revorder_config


# Constants
TAKE_PROFIT_THRESHOLD_MM = 0.05   # TP: MM pos increase sonrası min kâr ($0.05)
TAKE_PROFIT_THRESHOLD_LT = 0.05  # TP: PA/AN (LT) pos increase sonrası min kâr ($0.05) — UNIFIED with MM
TAKE_PROFIT_THRESHOLD = 0.05     # Default TP (backward compatibility)
RELOAD_THRESHOLD_LT = 0.08       # RL: TRIM/KB pos decrease sonrası min reload ($0.08)
RELOAD_THRESHOLD_MM = 0.13       # RL: MM pos decrease sonrası min reload ($0.13)
RELOAD_THRESHOLD = 0.08          # Default reload (backward compatibility)
L1_FRONT_RUN_RATIO = 0.15      # Phase 1: L1 önüne yazma oranı (spread * 0.15)
OB_FRONT_RUN_OFFSET = 0.01     # Phase 2: Orderbook kademe önüne yazma (sabit $0.01)


class RevOrderEngine:
    """
    Handles calculation of REV (Reverse) orders based on execution fills.
    
    2-Phase Pricing Strategy:
    - Phase 1: Use L1 bid/ask — maximizes profit capture
    - Phase 2: Scan orderbook levels — guarantees minimum threshold met
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or load_revorder_config()
        self.ob_fetcher = OrderBookFetcher()
        logger.info("[RevOrderEngine] Initialized with 2-Phase pricing (L1-first, Orderbook-fallback)")
    
    def _find_price_for_buy(
        self,
        symbol: str,
        fill_price: float,
        threshold: float,
        l1_bid: float,
        spread: float
    ) -> Tuple[Optional[float], str, int]:
        """
        Find optimal price for placing a BUY REV order (after a SELL fill).
        Goal: Buy back at maximum discount (lowest possible price that meets threshold).
        
        2-Phase Logic:
        PHASE 1: Check L1 bid → if (fill_price - bid) >= threshold
                 → BUY at bid + (spread * 0.15)  [proportional front-run]
        PHASE 2: If L1 bid doesn't meet threshold, scan orderbook BID levels
                 → Find first bid where (fill_price - bid) >= threshold
                 → BUY at bid + $0.01  [fixed front-run]
        
        Returns: (price, method, level)
        """
        # ═══════════════════════════════════════════════════════════════
        # PHASE 1: L1 BID CHECK (Max Profit Path — spread*0.15 offset)
        # ═══════════════════════════════════════════════════════════════
        if l1_bid > 0:
            l1_gap = fill_price - l1_bid
            if l1_gap >= threshold:
                front_offset = round(spread * L1_FRONT_RUN_RATIO, 4)
                target_price = round(l1_bid + front_offset, 2)
                logger.info(
                    f"[RevOrder] {symbol} BUY PHASE-1 ✅ L1 bid={l1_bid:.2f}, "
                    f"gap={l1_gap:.2f} >= {threshold}, "
                    f"offset=spread*0.15={front_offset:.3f}, target={target_price:.2f}"
                )
                return target_price, "L1_BID_FRONT", 1
            else:
                logger.info(
                    f"[RevOrder] {symbol} BUY PHASE-1 ✗ L1 bid={l1_bid:.2f}, "
                    f"gap={l1_gap:.2f} < {threshold}, falling to PHASE-2 (orderbook)"
                )

        # ═══════════════════════════════════════════════════════════════
        # PHASE 2: ORDERBOOK SCAN (Guaranteed Threshold Path)
        # ═══════════════════════════════════════════════════════════════
        bids, _ = self.ob_fetcher.fetch_orderbook(symbol, max_levels=10)
        
        if not bids:
            # FALLBACK: No orderbook → use fill_price - threshold (safe distance)
            fallback_price = round(fill_price - threshold, 2)
            logger.warning(
                f"[RevOrder] {symbol} BUY PHASE-2 No orderbook bids, "
                f"FALLBACK: fill ${fill_price:.2f} - ${threshold} = ${fallback_price:.2f}"
            )
            return fallback_price, "NO_ORDERBOOK_FALLBACK", 0
        
        logger.debug(f"[RevOrder] {symbol} Orderbook BIDS: {bids[:5]}")
        
        for level, (bid_price, qty) in enumerate(bids, start=1):
            gap = fill_price - bid_price
            
            if gap >= threshold:
                # Found suitable level - place $0.01 in front (fixed offset)
                target_price = round(bid_price + OB_FRONT_RUN_OFFSET, 2)
                
                logger.info(
                    f"[RevOrder] {symbol} BUY PHASE-2 ✅ "
                    f"Level {level} bid={bid_price:.2f}, gap={gap:.2f} >= {threshold}, "
                    f"target={target_price:.2f} (bid + ${OB_FRONT_RUN_OFFSET})"
                )
                return target_price, f"OB_LEVEL_{level}_FRONT", level
        
        # No suitable level in orderbook either — use fill_price - threshold as last resort
        fallback_price = round(fill_price - threshold, 2)
        logger.warning(
            f"[RevOrder] {symbol} BUY PHASE-2 No level with gap >= {threshold} "
            f"in {len(bids)} levels, FALLBACK: ${fallback_price:.2f}"
        )
        return fallback_price, "FILL_MINUS_THRESHOLD", 0
    
    def _find_price_for_sell(
        self,
        symbol: str,
        fill_price: float,
        threshold: float,
        l1_ask: float,
        spread: float
    ) -> Tuple[Optional[float], str, int]:
        """
        Find optimal price for placing a SELL REV order (after a BUY fill).
        Goal: Sell at maximum premium (highest possible price that meets threshold).
        
        2-Phase Logic:
        PHASE 1: Check L1 ask → if (ask - fill_price) >= threshold
                 → SELL at ask - (spread * 0.15)  [proportional front-run]
        PHASE 2: If L1 ask doesn't meet threshold, scan orderbook ASK levels
                 → Find first ask where (ask - fill_price) >= threshold
                 → SELL at ask - $0.01  [fixed front-run]
        
        Returns: (price, method, level)
        """
        # ═══════════════════════════════════════════════════════════════
        # PHASE 1: L1 ASK CHECK (Max Profit Path — spread*0.15 offset)
        # ═══════════════════════════════════════════════════════════════
        if l1_ask > 0:
            l1_gap = l1_ask - fill_price
            if l1_gap >= threshold:
                front_offset = round(spread * L1_FRONT_RUN_RATIO, 4)
                target_price = round(l1_ask - front_offset, 2)
                logger.info(
                    f"[RevOrder] {symbol} SELL PHASE-1 ✅ L1 ask={l1_ask:.2f}, "
                    f"gap={l1_gap:.2f} >= {threshold}, "
                    f"offset=spread*0.15={front_offset:.3f}, target={target_price:.2f}"
                )
                return target_price, "L1_ASK_FRONT", 1
            else:
                logger.info(
                    f"[RevOrder] {symbol} SELL PHASE-1 ✗ L1 ask={l1_ask:.2f}, "
                    f"gap={l1_gap:.2f} < {threshold}, falling to PHASE-2 (orderbook)"
                )

        # ═══════════════════════════════════════════════════════════════
        # PHASE 2: ORDERBOOK SCAN (Guaranteed Threshold Path)
        # ═══════════════════════════════════════════════════════════════
        _, asks = self.ob_fetcher.fetch_orderbook(symbol, max_levels=10)
        
        if not asks:
            # FALLBACK: No orderbook → use fill_price + threshold (safe distance)
            fallback_price = round(fill_price + threshold, 2)
            logger.warning(
                f"[RevOrder] {symbol} SELL PHASE-2 No orderbook asks, "
                f"FALLBACK: fill ${fill_price:.2f} + ${threshold} = ${fallback_price:.2f}"
            )
            return fallback_price, "NO_ORDERBOOK_FALLBACK", 0
        
        logger.debug(f"[RevOrder] {symbol} Orderbook ASKS: {asks[:5]}")
        
        for level, (ask_price, qty) in enumerate(asks, start=1):
            gap = ask_price - fill_price
            
            if gap >= threshold:
                # Found suitable level - place $0.01 in front (fixed offset)
                target_price = round(ask_price - OB_FRONT_RUN_OFFSET, 2)
                
                logger.info(
                    f"[RevOrder] {symbol} SELL PHASE-2 ✅ "
                    f"Level {level} ask={ask_price:.2f}, gap={gap:.2f} >= {threshold}, "
                    f"target={target_price:.2f} (ask - ${OB_FRONT_RUN_OFFSET})"
                )
                return target_price, f"OB_LEVEL_{level}_FRONT", level
        
        # No suitable level in orderbook either — use fill_price + threshold as last resort
        fallback_price = round(fill_price + threshold, 2)
        logger.warning(
            f"[RevOrder] {symbol} SELL PHASE-2 No level with gap >= {threshold} "
            f"in {len(asks)} levels, FALLBACK: ${fallback_price:.2f}"
        )
        return fallback_price, "FILL_PLUS_THRESHOLD", 0
    
    def calculate_rev_order(
        self,
        fill_event: Dict[str, Any],
        l1_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Calculates the REV order details based on the fill event and market data.
        
        2-Phase Pricing:
        Phase 1 (Easy Path): Use L1 ask/bid → MAX profit capture
        Phase 2 (Orderbook):  Scan levels → Guaranteed min threshold
        
        Args:
            fill_event: {symbol, action, qty, price, tag, account_id}
            l1_data: {bid, ask, spread}
        """
        try:
            symbol = fill_event['symbol']
            action = fill_event['action']  # BUY or SELL
            qty = fill_event['qty']
            fill_price = fill_event.get('price', 0.0)
            tag = fill_event.get('tag', '').upper()
            account_id = fill_event.get('account_id', 'UNKNOWN')
            
            # ── NEWCLMM EXCLUSION ──
            # NEWC-tagged fills have their own truth-tick-based TP mechanism.
            # REV must NOT create exit orders for them (would duplicate/conflict).
            if 'NEWC' in tag:
                logger.info(
                    f"[RevOrderEngine] {symbol} SKIP: NEWC-tagged fill "
                    f"(tag={tag}). NEWCLMM manages its own profit-taking."
                )
                return None
            
            bid = l1_data.get('bid', 0.0)
            ask = l1_data.get('ask', 0.0)
            spread = l1_data.get('spread', ask - bid if ask and bid else 0.0)
            
            # Minimum spread for calculations
            if spread <= 0:
                spread = 0.02  # Default 2 cents
            
            if fill_price <= 0:
                logger.warning(f"[RevOrderEngine] Invalid fill price for {symbol}: {fill_price}")
                return None

            # ═══════════════════════════════════════════════════════════════════
            # DETERMINE ORDER TYPE FROM TAG
            # ═══════════════════════════════════════════════════════════════════
            # LONG_INC  = Long artış (BUY fill)   -> SELL TP (kar al)
            # LONG_DEC  = Long azalış (SELL fill) -> BUY RELOAD (geri al)
            # SHORT_INC = Short artış (SELL fill) -> BUY TP (kar al)
            # SHORT_DEC = Short azalış (BUY fill) -> SELL RELOAD (geri sat)
            
            is_long = "LONG" in tag
            is_short = "SHORT" in tag
            is_increase = "INC" in tag  # Also catches legacy INCREASE
            is_decrease = "DEC" in tag  # Also catches legacy DECREASE
            
            # Default to INCREASE if tag is ambiguous
            if not is_increase and not is_decrease:
                is_increase = True
            
            # Default direction from fill action
            if not is_long and not is_short:
                is_long = (action == 'BUY')
                is_short = (action == 'SELL')
            
            # ═══════════════════════════════════════════════════════════════════
            # DETERMINE REV ORDER TYPE AND THRESHOLD
            # ═══════════════════════════════════════════════════════════════════
            # INCREASE fill (POS↑) → Take Profit → ALL sources: $0.05
            # DECREASE fill (POS↓) → Reload → source-specific:
            #   - MM pos decrease: $0.13 (agresif, daha geniş spread)
            #   - LT/KB pos decrease: $0.08
            #   - PA/AN = increase-only engines → always TP ($0.05→$0.09), never RL
            
            # Detect source (ENGINE TAG) for threshold selection
            # ═══════════════════════════════════════════════════════════════════
            # v4 tag format: {POS}_{ENGINE}_{DIR}_{ACTION}
            #   LT_PA_LONG_INC → parts[1] = PA
            #   MM_MM_LONG_INC → parts[1] = MM
            #   MM_KB_LONG_DEC → parts[1] = KB
            # Legacy fallback: KARBOTU_LONG_DEC, PATADD_LONG_INC, etc.
            # ═══════════════════════════════════════════════════════════════════
            source = "MM"  # Default
            clean_tag = tag.replace('FR_', '').replace('OZEL_', '')  # Remove frontlama/tasfiye prefix
            
            # v4 format: try parsing parts[1] as ENGINE TAG
            tag_parts = clean_tag.split('_')
            if len(tag_parts) >= 4 and tag_parts[0] in ('MM', 'LT'):
                engine_candidate = tag_parts[1]
                if engine_candidate in ('MM', 'PA', 'AN', 'KB', 'TRIM', 'NEWC'):
                    source = engine_candidate
                else:
                    source = "MM"  # Unknown engine → default
            else:
                # Legacy tag format fallback
                if 'TRIM' in clean_tag:
                    source = "TRIM"
                elif clean_tag.startswith('KARBOTU') or clean_tag.startswith('HEAVY'):
                    source = "KB"
                elif clean_tag.startswith('PATADD') or clean_tag.startswith('PAT'):
                    source = "PA"
                elif clean_tag.startswith('ADDNEWPOS'):
                    source = "AN"
                elif clean_tag.startswith('MM_') or 'CHURN' in clean_tag:
                    source = "MM"
                elif clean_tag.startswith('LT_'):
                    source = "TRIM"  # Legacy LT_ tags are from TRIM engine
            
            # ═══════════════════════════════════════════════════════════════════
            # THRESHOLD SELECTION — DEPENDS ON POS TAG, NOT ENGINE TAG
            # ═══════════════════════════════════════════════════════════════════
            # POS TAG = MM → TP $0.05, RL $0.13
            # POS TAG = LT → TP $0.09, RL $0.08
            #
            # Reasoning: Threshold reflects the POSITION's character, not the engine.
            # An MM position trimmed by KB still has MM-level reload ($0.13)
            # because the position itself is short-term (MM).
            # ═══════════════════════════════════════════════════════════════════
            
            # Extract POS TAG early for threshold selection
            pos_tag_for_threshold = "MM"  # Default
            if len(tag_parts) >= 4 and tag_parts[0] in ('MM', 'LT'):
                pos_tag_for_threshold = tag_parts[0]
            elif clean_tag.startswith('LT_') or clean_tag.startswith('LT '):
                pos_tag_for_threshold = "LT"
            
            if is_increase:
                # POS INCREASE → Take Profit
                # Reachable by: MM (INC), PA (INC), AN (INC)
                # NOT reachable by: KB, TRIM (always DEC → RL branch)
                rev_type = "TP"
                if pos_tag_for_threshold == "LT":
                    threshold = TAKE_PROFIT_THRESHOLD_LT  # $0.09 (LT pozisyon)
                else:
                    threshold = TAKE_PROFIT_THRESHOLD_MM  # $0.05 (MM pozisyon)
            else:
                # POS DECREASE → Reload
                # Reachable by: MM (DEC), KB (DEC), TRIM (DEC)
                # NOT reachable by: PA, AN (always INC → TP branch)
                rev_type = "RL"
                if pos_tag_for_threshold == "MM":
                    threshold = RELOAD_THRESHOLD_MM       # $0.13 (MM pozisyon)
                else:
                    threshold = RELOAD_THRESHOLD_LT       # $0.08 (LT pozisyon)
            
            # REV action is opposite of fill action
            rev_action = 'SELL' if action == 'BUY' else 'BUY'
            
            # ═══════════════════════════════════════════════════════════════════
            # 2-PHASE PRICING: L1 FIRST, ORDERBOOK FALLBACK
            # ═══════════════════════════════════════════════════════════════════
            rev_price = 0.0
            method = "UNKNOWN"
            level = 0
            
            if rev_action == 'BUY':
                # Need to buy (cover short / reload long) → look at BID side
                rev_price, method, level = self._find_price_for_buy(
                    symbol, fill_price, threshold, bid, spread
                )
            else:
                # Need to sell (take profit) → look at ASK side
                rev_price, method, level = self._find_price_for_sell(
                    symbol, fill_price, threshold, ask, spread
                )
            
            if not rev_price or rev_price <= 0:
                logger.warning(f"[RevOrder] {symbol} Could not determine price, skipping")
                return None
            
            # ═══════════════════════════════════════════════════════════════════
            # GENERATE TAG — v4 Format: REV_{TYPE}_{POS}_{ENGINE}_{ACTION}
            # ═══════════════════════════════════════════════════════════════════
            # TYPE   = TP (Take Profit) or RL (Reload)
            # POS    = MM or LT (position type in portfolio)
            # ENGINE = MM, PA, AN, KB, TRIM (which engine's fill triggered REV)
            # ACTION = BUY or SELL (what the REV order does)
            #
            # Examples:
            #   LT_PA_LONG_INC fill  → REV_TP_LT_PA_SELL  (sell to take profit)
            #   MM_MM_SHORT_DEC fill → REV_RL_MM_MM_SELL   (sell to reload short)
            #   MM_KB_LONG_DEC fill  → REV_RL_MM_KB_BUY    (buy to reload long)
            # ═══════════════════════════════════════════════════════════════════
            
            # Extract POS TAG from fill event tag prefix (first 2 chars: MM or LT)
            pos_tag = "MM"  # Default
            if clean_tag.startswith('LT_') or clean_tag.startswith('LT '):
                pos_tag = "LT"
            elif clean_tag.startswith('MM_') or clean_tag.startswith('MM '):
                pos_tag = "MM"
            
            rev_tag = f"REV_{rev_type}_{pos_tag}_{source}_{rev_action}"
            
            # Calculate actual gap for logging
            if rev_action == 'BUY':
                actual_gap = fill_price - rev_price
            else:
                actual_gap = rev_price - fill_price
            
            logger.info(
                f"[RevOrder] ✅ {symbol} {rev_action} {qty} @ ${rev_price:.2f} | "
                f"Tag: {rev_tag} | Type: {rev_type} | POS: {pos_tag} | ENGINE: {source} | "
                f"Profit/Save: ${actual_gap:.2f} | Threshold: ${threshold} | Method: {method}"
            )
            
            # === Comprehensive REV Order Context Log ===
            try:
                from app.core.order_context_logger import format_rev_order_log, get_order_context
                _rev_ctx = get_order_context(symbol)
                logger.info(format_rev_order_log(
                    symbol=symbol, rev_action=rev_action, qty=qty,
                    rev_price=rev_price, tag=rev_tag, rev_type=rev_type,
                    method=method, fill_action=action, fill_price=fill_price,
                    bid=bid, ask=ask, profit_save=actual_gap, ctx=_rev_ctx
                ))
            except Exception:
                pass
            
            return {
                'symbol': symbol,
                'action': rev_action,
                'qty': qty,
                'price': round(rev_price, 2),
                'hidden': True,  # QUANT_ENGINE CORE RULE: ALL ORDERS HIDDEN
                'tag': rev_tag,
                'method': method,
                'rev_type': rev_type,
                'pos_tag': pos_tag,
                'engine_source': source,
                'threshold': threshold,
                'fill_price': fill_price,
                'level': level,
                'spread': spread,
                'original_fill_id': fill_event.get('order_id', ''),
                'source_engine': source
            }
            
        except Exception as e:
            logger.error(f"[RevOrderEngine] Error calculating REV for {fill_event.get('symbol', 'UNKNOWN')}: {e}", exc_info=True)
            return None


# Global instance management
_engine_instance = None


def get_revorder_engine(config: Optional[Dict] = None):
    """Singleton getter for RevOrderEngine"""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = RevOrderEngine(config)
    return _engine_instance
