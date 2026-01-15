"""
ADDNEWPOS Core Strategy - Portfolio Construction

Aim: Add LONG positions while respecting Port Adjuster group caps.

Rules:
- Port Adjuster snapshot used
- group max_lot not exceeded
- FINAL_THG / FBTOT / SMA63 / SMA246 filters
- Spread & AVG_ADV filters

Output: OrderProposal (BUY / ADD)
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from app.core.logger import logger
from app.psfalgo.proposal_models import OrderProposal
from app.psfalgo.market_snapshot_models import MarketSnapshot
from app.psfalgo.decision_models import PositionSnapshot
from app.strategies.strategy_context import StrategyContext
from app.market_data.grouping import resolve_group_key


def generate_proposals(
    market_snapshots: Dict[str, MarketSnapshot],
    position_snapshots: Dict[str, PositionSnapshot],
    context: StrategyContext
) -> List[OrderProposal]:
    """
    Generate BUY/ADD proposals for portfolio construction.
    
    Args:
        market_snapshots: Dict mapping symbol -> MarketSnapshot
        position_snapshots: Dict mapping symbol -> PositionSnapshot
        context: StrategyContext (Port Adjuster, GRPAN, etc.)
        
    Returns:
        List of OrderProposal (BUY or ADD)
    """
    proposals = []
    
    # Get Port Adjuster snapshot
    port_adjuster_snapshot = context.get_port_adjuster_snapshot()
    if not port_adjuster_snapshot:
        logger.warning("[ADDNEWPOS_CORE] Port Adjuster snapshot not available")
        return proposals
    
    # Calculate current group positions
    group_current_lots: Dict[str, float] = {}
    for symbol, position in position_snapshots.items():
        if position.is_long and position.qty > 0:
            static_data = context.get_static_data(symbol)
            if static_data:
                group_key = resolve_group_key(static_data)
                if group_key:
                    group_current_lots[group_key] = group_current_lots.get(group_key, 0.0) + position.qty
    
    # Process symbols without positions (or with small positions)
    for symbol, market in market_snapshots.items():
        # Skip if already has significant position
        existing_position = position_snapshots.get(symbol)
        if existing_position and existing_position.is_long and existing_position.qty >= 500:
            continue  # Already has position, skip
        
        # Get static data
        static_data = context.get_static_data(symbol)
        if not static_data:
            continue
        
        # Resolve group key
        group_key = resolve_group_key(static_data)
        if not group_key:
            continue
        
        # Check Port Adjuster group cap
        group_allocation = port_adjuster_snapshot.long_allocations.get(group_key)
        if not group_allocation:
            continue  # Group not in Port Adjuster config
        
        group_max_lot = group_allocation.max_lot
        current_group_lot = group_current_lots.get(group_key, 0.0)
        remaining_capacity = group_max_lot - current_group_lot
        
        if remaining_capacity < 100:  # Not enough capacity for minimum lot
            continue
        
        # Filters
        
        # 1. FINAL_THG filter (must be positive/above threshold)
        final_thg = static_data.get('FINAL_THG')
        if not final_thg or final_thg < 0.5:
            continue
        
        # 2. FBTOT filter (must be below threshold = not overpriced)
        if not market.fbtot or market.fbtot > 1.10:
            continue
        
        # 3. SMA63 filter (positive change preferred)
        if market.sma63_chg and market.sma63_chg < -2.0:
            continue  # SMA63 declining too much
        
        # 4. SMA246 filter (positive change preferred)
        if market.sma246_chg and market.sma246_chg < -2.0:
            continue  # SMA246 declining too much
        
        # 5. Spread filter (not too wide)
        if not market.spread_percent or market.spread_percent > 1.0:
            continue
        
        # 6. AVG_ADV filter (minimum liquidity)
        avg_adv = static_data.get('AVG_ADV')
        if not avg_adv or avg_adv < 10000:
            continue  # Too illiquid
        
        # Calculate proposed lot
        # Use remaining group capacity, but cap at reasonable size
        proposed_lot = min(remaining_capacity, 1000)  # Max 1000 lot per symbol
        if proposed_lot < 100:
            proposed_lot = 100
        
        # Round to nearest 100
        proposed_lot = int((proposed_lot + 50) // 100) * 100
        
        # Proposed price: Use bid (we're buying)
        proposed_price = market.bid if market.bid else market.last
        
        # Determine side: ADD if already has position, BUY if new
        side = "ADD" if existing_position and existing_position.is_long else "BUY"
        
        # Build reason
        reason_parts = [
            f"FINAL_THG {final_thg:.2f}",
            f"FBTOT {market.fbtot:.2f}",
            f"Group {group_key} cap {remaining_capacity:.0f} remaining"
        ]
        if market.sma63_chg:
            reason_parts.append(f"SMA63 {market.sma63_chg:+.2f}")
        if market.sma246_chg:
            reason_parts.append(f"SMA246 {market.sma246_chg:+.2f}")
        
        # Confidence based on signals
        confidence = 0.5  # Base
        if final_thg > 1.0:
            confidence += 0.2
        if market.fbtot and market.fbtot < 1.05:
            confidence += 0.15
        if market.sma63_chg and market.sma63_chg > 0:
            confidence += 0.1
        if market.sma246_chg and market.sma246_chg > 0:
            confidence += 0.05
        
        # Create proposal
        proposal = OrderProposal(
            symbol=symbol,
            side=side,
            qty=proposed_lot,
            order_type="LIMIT",
            proposed_price=proposed_price,
            bid=market.bid,
            ask=market.ask,
            last=market.last,
            spread=market.spread,
            spread_percent=market.spread_percent,
            engine="ADDNEWPOS_CORE",
            reason=" | ".join(reason_parts),
            confidence=min(confidence, 1.0),
            metrics_used={
                'final_thg': final_thg or 0.0,
                'fbtot': market.fbtot or 0.0,
                'sma63_chg': market.sma63_chg or 0.0,
                'sma246_chg': market.sma246_chg or 0.0,
                'spread_percent': market.spread_percent or 0.0,
                'avg_adv': avg_adv or 0.0,
                'group_key': group_key,
                'remaining_capacity': remaining_capacity
            }
        )
        
        proposals.append(proposal)
        logger.debug(f"[ADDNEWPOS_CORE] Generated proposal: {symbol} {side} {proposed_lot} @ {proposed_price} (group={group_key}, remaining={remaining_capacity:.0f})")
    
    return proposals





