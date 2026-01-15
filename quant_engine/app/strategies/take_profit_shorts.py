"""
Take Profit Shorts Strategy

Aim: Cover SHORT positions when favorable.

Signals used:
- GRPAN support level
- RWVAP upward break
- Spread narrowing
- SFSTOT / GORT
- Befday → Today PnL

Output: OrderProposal with side=BUY_TO_COVER
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from app.core.logger import logger
from app.psfalgo.proposal_models import OrderProposal
from app.psfalgo.market_snapshot_models import MarketSnapshot
from app.psfalgo.decision_models import PositionSnapshot
from app.strategies.strategy_context import StrategyContext


def generate_proposals(
    market_snapshots: Dict[str, MarketSnapshot],
    position_snapshots: Dict[str, PositionSnapshot],
    context: StrategyContext
) -> List[OrderProposal]:
    """
    Generate cover proposals for SHORT positions.
    
    Args:
        market_snapshots: Dict mapping symbol -> MarketSnapshot
        position_snapshots: Dict mapping symbol -> PositionSnapshot
        context: StrategyContext (GRPAN, RWVAP, etc.)
        
    Returns:
        List of OrderProposal (BUY_TO_COVER)
    """
    proposals = []
    
    for symbol, position in position_snapshots.items():
        # Only process SHORT positions
        if not position.is_short or position.qty >= 0:
            continue
        
        market = market_snapshots.get(symbol)
        if not market:
            continue
        
        # Get GRPAN metrics
        grpan_data = context.get_grpan_for_symbol(symbol)
        grpan_price = grpan_data.get('grpan_price')
        grpan_deviation = None
        if market.last and grpan_price:
            grpan_deviation = market.last - grpan_price  # Negative if last < grpan (support)
        
        # Get RWVAP metrics
        rwvap_1d = context.get_rwvap_for_symbol(symbol, window='1D')
        rwvap_price = rwvap_1d.get('rwvap')
        rwvap_deviation = None
        if market.last and rwvap_price:
            rwvap_deviation = market.last - rwvap_price  # Negative if last < rwvap (support)
        
        # Calculate PnL (for shorts, positive PnL = price went down = good)
        pnl_percent = position.pnl_percent
        
        # Decision logic: When to cover short?
        # 1. Price reached GRPAN support (last < grpan)
        # 2. Price reached RWVAP support (last < rwvap)
        # 3. Spread narrowing (liquidity improving)
        # 4. SFSTOT / GORT signals
        # 5. Profit target reached
        
        should_cover = False
        reason_parts = []
        confidence = 0.0
        
        # GRPAN support level (last below GRPAN = support reached)
        if grpan_deviation and grpan_deviation < -0.3 and grpan_price:
            deviation_pct = abs(grpan_deviation / grpan_price) * 100
            if deviation_pct > 1.0:  # Last is 1%+ below GRPAN (support)
                should_cover = True
                reason_parts.append(f"GRPAN support -{deviation_pct:.2f}%")
                confidence += 0.3
        
        # RWVAP support level
        if rwvap_deviation and rwvap_deviation < -0.3 and rwvap_price:
            deviation_pct = abs(rwvap_deviation / rwvap_price) * 100
            if deviation_pct > 1.0:  # Last is 1%+ below RWVAP (support)
                should_cover = True
                reason_parts.append(f"RWVAP support -{deviation_pct:.2f}%")
                confidence += 0.3
        
        # Spread narrowing (spread getting tighter = better liquidity)
        if market.spread_percent and market.spread_percent < 0.5:
            should_cover = True
            reason_parts.append(f"Spread narrow {market.spread_percent:.2f}%")
            confidence += 0.2
        
        # SFSTOT signal (short front sell total)
        if market.sfstot and market.sfstot < 0.9:  # SFSTOT low = good for covering
            should_cover = True
            reason_parts.append(f"SFSTOT {market.sfstot:.2f}")
            confidence += 0.15
        
        # GORT signal
        if market.gort and market.gort < -0.5:  # GORT negative = good for covering
            should_cover = True
            reason_parts.append(f"GORT {market.gort:.2f}")
            confidence += 0.15
        
        # Profit target (PnL positive for shorts = price went down)
        if pnl_percent > 1.5:
            should_cover = True
            reason_parts.append(f"PnL {pnl_percent:.2f}%")
            confidence += 0.2
        
        if not should_cover or not reason_parts:
            continue
        
        # Calculate cover quantity (percentage of position)
        if confidence >= 0.7:
            lot_percentage = 100.0  # Full cover
        elif confidence >= 0.5:
            lot_percentage = 50.0
        else:
            lot_percentage = 25.0
        
        cover_qty = int((abs(position.qty) * lot_percentage) / 100.0)
        if cover_qty < 100:
            cover_qty = 100
        # Round to nearest 100
        cover_qty = int((cover_qty + 50) // 100) * 100
        
        # Proposed price: Use bid (we're buying to cover)
        proposed_price = market.bid if market.bid else market.last
        
        # Create proposal
        proposal = OrderProposal(
            symbol=symbol,
            side="BUY_TO_COVER",
            qty=cover_qty,
            order_type="LIMIT",
            proposed_price=proposed_price,
            bid=market.bid,
            ask=market.ask,
            last=market.last,
            spread=market.spread,
            spread_percent=market.spread_percent,
            engine="TAKE_PROFIT_SHORT",
            reason=" | ".join(reason_parts),
            confidence=min(confidence, 1.0),
            metrics_used={
                'pnl_percent': pnl_percent,
                'sfstot': market.sfstot or 0.0,
                'gort': market.gort or 0.0,
                'grpan_deviation': grpan_deviation or 0.0,
                'rwvap_deviation': rwvap_deviation or 0.0,
                'spread_percent': market.spread_percent or 0.0
            },
            lot_percentage=lot_percentage,
            price_hint=grpan_price or rwvap_price
        )
        
        proposals.append(proposal)
        logger.debug(f"[TAKE_PROFIT_SHORT] Generated proposal: {symbol} BUY_TO_COVER {cover_qty} @ {proposed_price} (confidence={confidence:.2f})")
    
    return proposals





