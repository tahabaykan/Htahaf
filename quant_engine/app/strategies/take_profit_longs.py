"""
Take Profit Longs Strategy

Aim: Lock profits from existing LONG positions.

Signals used:
- bid / ask / last
- spread %
- GRPAN deviation (last vs grpan)
- RWVAP deviation
- FBTOT / GORT (overpricing feeling)
- Befday → Today PnL

Output: OrderProposal with side=SELL or ASK_SELL
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
    Generate take-profit proposals for LONG positions.
    
    Args:
        market_snapshots: Dict mapping symbol -> MarketSnapshot
        position_snapshots: Dict mapping symbol -> PositionSnapshot
        context: StrategyContext (GRPAN, RWVAP, etc.)
        
    Returns:
        List of OrderProposal (SELL or ASK_SELL)
    """
    proposals = []
    
    for symbol, position in position_snapshots.items():
        # Only process LONG positions
        if not position.is_long or position.qty <= 0:
            continue
        
        market = market_snapshots.get(symbol)
        if not market:
            continue
        
        # Get GRPAN metrics
        grpan_data = context.get_grpan_for_symbol(symbol)
        grpan_price = grpan_data.get('grpan_price')
        grpan_deviation = None
        if market.last and grpan_price:
            grpan_deviation = market.last - grpan_price
        
        # Get RWVAP metrics
        rwvap_1d = context.get_rwvap_for_symbol(symbol, window='1D')
        rwvap_price = rwvap_1d.get('rwvap')
        rwvap_deviation = None
        if market.last and rwvap_price:
            rwvap_deviation = market.last - rwvap_price
        
        # Calculate PnL metrics
        pnl_percent = position.pnl_percent
        today_pnl = position.unrealized_pnl  # Already calculated in PositionSnapshot
        
        # Decision logic: When to take profit?
        # 1. PnL threshold (e.g., > 2%)
        # 2. Overpricing signals (FBTOT > threshold, GORT > threshold)
        # 3. GRPAN deviation (last > grpan by X%)
        # 4. RWVAP deviation (last > rwvap by X%)
        # 5. Spread acceptable (not too wide)
        
        should_take_profit = False
        reason_parts = []
        confidence = 0.0
        
        # PnL check
        if pnl_percent > 2.0:
            should_take_profit = True
            reason_parts.append(f"PnL {pnl_percent:.2f}%")
            confidence += 0.3
        
        # FBTOT overpricing
        if market.fbtot and market.fbtot > 1.10:
            should_take_profit = True
            reason_parts.append(f"FBTOT {market.fbtot:.2f} (overpriced)")
            confidence += 0.2
        
        # GORT overpricing
        if market.gort and market.gort > 1.0:
            should_take_profit = True
            reason_parts.append(f"GORT {market.gort:.2f} (overpriced)")
            confidence += 0.2
        
        # GRPAN deviation (last significantly above GRPAN)
        if grpan_deviation and grpan_deviation > 0.5 and grpan_price:
            deviation_pct = (grpan_deviation / grpan_price) * 100
            if deviation_pct > 2.0:  # Last is 2%+ above GRPAN
                should_take_profit = True
                reason_parts.append(f"GRPAN dev +{deviation_pct:.2f}%")
                confidence += 0.15
        
        # RWVAP deviation
        if rwvap_deviation and rwvap_deviation > 0.5 and rwvap_price:
            deviation_pct = (rwvap_deviation / rwvap_price) * 100
            if deviation_pct > 2.0:  # Last is 2%+ above RWVAP
                should_take_profit = True
                reason_parts.append(f"RWVAP dev +{deviation_pct:.2f}%")
                confidence += 0.15
        
        # Spread check (don't sell if spread is too wide)
        if market.spread_percent and market.spread_percent > 1.0:
            should_take_profit = False  # Spread too wide, wait
            reason_parts.append(f"Spread {market.spread_percent:.2f}% too wide")
        
        if not should_take_profit or not reason_parts:
            continue
        
        # Calculate sell quantity (percentage of position)
        # Conservative: sell 25-50% if multiple signals, 100% if very strong
        if confidence >= 0.7:
            lot_percentage = 100.0  # Full position
        elif confidence >= 0.5:
            lot_percentage = 50.0
        else:
            lot_percentage = 25.0
        
        sell_qty = int((position.qty * lot_percentage) / 100.0)
        if sell_qty < 100:  # Minimum lot size
            sell_qty = 100
        # Round to nearest 100
        sell_qty = int((sell_qty + 50) // 100) * 100
        
        # Proposed price: Use ask (we're selling)
        proposed_price = market.ask if market.ask else market.last
        
        # Create proposal
        proposal = OrderProposal(
            symbol=symbol,
            side="SELL",
            qty=sell_qty,
            order_type="LIMIT",
            proposed_price=proposed_price,
            bid=market.bid,
            ask=market.ask,
            last=market.last,
            spread=market.spread,
            spread_percent=market.spread_percent,
            engine="TAKE_PROFIT_LONG",
            reason=" | ".join(reason_parts),
            confidence=min(confidence, 1.0),
            metrics_used={
                'pnl_percent': pnl_percent,
                'fbtot': market.fbtot or 0.0,
                'gort': market.gort or 0.0,
                'grpan_deviation': grpan_deviation or 0.0,
                'rwvap_deviation': rwvap_deviation or 0.0,
                'spread_percent': market.spread_percent or 0.0
            },
            lot_percentage=lot_percentage,
            price_hint=grpan_price or rwvap_price
        )
        
        proposals.append(proposal)
        logger.debug(f"[TAKE_PROFIT_LONG] Generated proposal: {symbol} SELL {sell_qty} @ {proposed_price} (confidence={confidence:.2f})")
    
    return proposals





