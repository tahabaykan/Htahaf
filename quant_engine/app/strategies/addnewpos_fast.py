"""
ADDNEWPOS Fast Strategy - Spread / Micro Alpha

Aim: Short-term spread / print anomaly opportunities.

Signals used:
- GRPAN (last print deviation)
- GOD / ROD
- Spread edge
- Micro liquidity

Features:
- Small lot sizes
- Feature flag enabled/disabled
- Default: DISABLED
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from app.core.logger import logger
from app.psfalgo.proposal_models import OrderProposal
from app.psfalgo.market_snapshot_models import MarketSnapshot
from app.psfalgo.decision_models import PositionSnapshot
from app.strategies.strategy_context import StrategyContext


# Feature flag: Enable/disable this strategy
ENABLED = False  # Default: DISABLED


def generate_proposals(
    market_snapshots: Dict[str, MarketSnapshot],
    position_snapshots: Dict[str, PositionSnapshot],
    context: StrategyContext
) -> List[OrderProposal]:
    """
    Generate fast BUY proposals for micro alpha opportunities.
    
    Args:
        market_snapshots: Dict mapping symbol -> MarketSnapshot
        position_snapshots: Dict mapping symbol -> PositionSnapshot
        context: StrategyContext (GRPAN, RWVAP, etc.)
        
    Returns:
        List of OrderProposal (BUY) - small lot sizes
    """
    proposals = []
    
    # Check feature flag
    if not ENABLED:
        return proposals
    
    for symbol, market in market_snapshots.items():
        # Skip if already has position
        if symbol in position_snapshots:
            continue
        
        # Get static data
        static_data = context.get_static_data(symbol)
        if not static_data:
            continue
        
        # Get GRPAN metrics
        grpan_all_windows = context.get_grpan_all_windows(symbol)
        if not grpan_all_windows:
            continue
        
        # Calculate GOD (GRPAN ORT DEV)
        window_names = ['pan_10m', 'pan_30m', 'pan_1h', 'pan_3h', 'pan_1d', 'pan_3d']
        valid_grpan_prices = []
        for window_name in window_names:
            window_data = grpan_all_windows.get(window_name, {})
            grpan_price = window_data.get('grpan_price')
            if grpan_price and isinstance(grpan_price, (int, float)):
                valid_grpan_prices.append(float(grpan_price))
        
        if not valid_grpan_prices or not market.last:
            continue
        
        grpan_ort = sum(valid_grpan_prices) / len(valid_grpan_prices)
        god = market.last - grpan_ort  # GOD = last - grpan_ort
        
        # Get RWVAP metrics
        rwvap_all = context.get_rwvap_all_windows(symbol)
        if not rwvap_all:
            continue
        
        # Calculate ROD (RWVAP ORT DEV)
        rwvap_window_names = ['rwvap_1d', 'rwvap_3d', 'rwvap_5d']
        valid_rwvap_prices = []
        for window_name in rwvap_window_names:
            window_data = rwvap_all.get(window_name, {})
            rwvap_price = window_data.get('rwvap') or window_data.get('rwvap_price')
            if rwvap_price and isinstance(rwvap_price, (int, float)):
                valid_rwvap_prices.append(float(rwvap_price))
        
        if not valid_rwvap_prices:
            continue
        
        rwvap_ort = sum(valid_rwvap_prices) / len(valid_rwvap_prices)
        rod = market.last - rwvap_ort  # ROD = last - rwvap_ort
        
        # Decision logic: Micro alpha opportunities
        # 1. GOD negative (last below GRPAN ORT = cheap)
        # 2. ROD negative (last below RWVAP ORT = cheap)
        # 3. Spread tight (good liquidity)
        # 4. Small lot (micro position)
        
        should_buy = False
        reason_parts = []
        confidence = 0.0
        
        # GOD signal (negative = cheap)
        if god < -0.3:
            deviation_pct = abs(god / grpan_ort) * 100 if grpan_ort > 0 else 0
            if deviation_pct > 1.0:  # Last is 1%+ below GRPAN ORT
                should_buy = True
                reason_parts.append(f"GOD {god:.2f} ({deviation_pct:.2f}% below GRPAN ORT)")
                confidence += 0.4
        
        # ROD signal (negative = cheap)
        if rod < -0.3:
            deviation_pct = abs(rod / rwvap_ort) * 100 if rwvap_ort > 0 else 0
            if deviation_pct > 1.0:  # Last is 1%+ below RWVAP ORT
                should_buy = True
                reason_parts.append(f"ROD {rod:.2f} ({deviation_pct:.2f}% below RWVAP ORT)")
                confidence += 0.3
        
        # Spread check (must be tight for micro alpha)
        if not market.spread_percent or market.spread_percent > 0.5:
            should_buy = False  # Spread too wide for micro alpha
        
        if not should_buy or not reason_parts:
            continue
        
        # Small lot size (micro position)
        proposed_lot = 100  # Minimum lot for micro alpha
        
        # Proposed price: Use bid (we're buying)
        proposed_price = market.bid if market.bid else market.last
        
        # Create proposal
        proposal = OrderProposal(
            symbol=symbol,
            side="BUY",
            qty=proposed_lot,
            order_type="LIMIT",
            proposed_price=proposed_price,
            bid=market.bid,
            ask=market.ask,
            last=market.last,
            spread=market.spread,
            spread_percent=market.spread_percent,
            engine="ADDNEWPOS_FAST",
            reason=" | ".join(reason_parts),
            confidence=min(confidence, 1.0),
            metrics_used={
                'god': god,
                'rod': rod,
                'grpan_ort': grpan_ort,
                'rwvap_ort': rwvap_ort,
                'spread_percent': market.spread_percent or 0.0
            },
            price_hint=grpan_ort or rwvap_ort
        )
        
        proposals.append(proposal)
        logger.debug(f"[ADDNEWPOS_FAST] Generated proposal: {symbol} BUY {proposed_lot} @ {proposed_price} (GOD={god:.2f}, ROD={rod:.2f})")
    
    return proposals





