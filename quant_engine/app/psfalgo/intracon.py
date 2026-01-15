"""
IntraCon - Intraday Controller

Gün içi pozisyon değişikliklerini kontrol eden merkezi yapı.

Sorumluluklar:
1. BEFDAY Tracking: befday_qty, current_qty, todays_qty_chg
2. Portfolio % MAXALW Lot Limit: Portföy yüzdesine göre günlük eklenebilecek lot
3. Daily Limit Enforcement: Gün içi limit doluysa yeni emir yok
4. 100-Lot Rounding: Tüm ADDNEWPOS emirleri 100'lük yuvarlama

Example:
    CIM-PRD: MAXALW=7500, current_qty=3000 (portfolio %10)
    Rule: >= 10% → MAXALW × 0.05 = 375 → rounded to 400 lot
    If todays_qty_chg already +400, no more adds allowed today.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Dict, Any, Optional, List, Tuple
import json
import os
from app.core.logger import logger


# ============================================================================
# Constants
# ============================================================================

# Portfolio % → (max_pct, maxalw_multiplier)
PORTFOLIO_RULES = [
    {'max_pct': 1.0,  'multiplier': 0.50, 'description': 'Yeni pozisyon'},
    {'max_pct': 3.0,  'multiplier': 0.40, 'description': 'Küçük pozisyon'},
    {'max_pct': 5.0,  'multiplier': 0.30, 'description': 'Orta pozisyon'},
    {'max_pct': 7.0,  'multiplier': 0.20, 'description': 'Büyük pozisyon'},
    {'max_pct': 10.0, 'multiplier': 0.10, 'description': 'Çok büyük pozisyon'},
    {'max_pct': 100.0, 'multiplier': 0.05, 'description': 'Maksimum doluluk'},
]

MIN_LOT_SIZE = 200  # Minimum emir lot'u


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class SymbolIntraday:
    """Tek sembol için gün içi durum"""
    symbol: str
    maxalw: int = 0
    
    # BEFDAY values (from start of day snapshot)
    befday_qty: int = 0
    befday_avg_cost: float = 0.0
    
    # Current values (live)
    current_qty: int = 0
    current_avg_cost: float = 0.0
    current_price: float = 0.0
    
    # Pending orders (açık emirler dolunca olacak miktar)
    pending_buy_qty: int = 0  # Açık alış emirleri (pozitif)
    pending_sell_qty: int = 0  # Açık satış emirleri (negatif olarak hesaplanır)
    
    # Potential values (current + pending orders)
    potential_qty: int = 0  # current_qty + pending orders
    potential_pct: float = 0.0  # Potential % of portfolio
    
    # Calculated
    todays_qty_chg: int = 0  # current_qty - befday_qty
    todays_add_limit: int = 0  # Max lot that can be added today based on portfolio %
    todays_add_used: int = 0  # How much of the limit has been used
    todays_add_remaining: int = 0  # Remaining add capacity
    
    # Portfolio metrics
    portfolio_pct: float = 0.0  # % of total portfolio
    applicable_rule: str = ""  # Which rule applies
    
    # MAXALW validation
    maxalw_exceeded: bool = False  # current_qty >= maxalw
    potential_exceeds_maxalw: bool = False  # potential_qty > maxalw
    maxalw_headroom: int = 0  # maxalw - abs(current_qty)
    potential_maxalw_headroom: int = 0  # maxalw - abs(potential_qty)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'symbol': self.symbol,
            'maxalw': self.maxalw,
            'befday_qty': self.befday_qty,
            'befday_avg_cost': self.befday_avg_cost,
            'current_qty': self.current_qty,
            'current_avg_cost': self.current_avg_cost,
            'current_price': self.current_price,
            'pending_buy_qty': self.pending_buy_qty,
            'pending_sell_qty': self.pending_sell_qty,
            'potential_qty': self.potential_qty,
            'potential_pct': self.potential_pct,
            'todays_qty_chg': self.todays_qty_chg,
            'todays_add_limit': self.todays_add_limit,
            'todays_add_used': self.todays_add_used,
            'todays_add_remaining': self.todays_add_remaining,
            'portfolio_pct': self.portfolio_pct,
            'applicable_rule': self.applicable_rule,
            'maxalw_exceeded': self.maxalw_exceeded,
            'potential_exceeds_maxalw': self.potential_exceeds_maxalw,
            'maxalw_headroom': self.maxalw_headroom,
            'potential_maxalw_headroom': self.potential_maxalw_headroom
        }


@dataclass
class IntraConSnapshot:
    """Full IntraCon snapshot for a mode"""
    mode: str  # hampro, ibkr_ped, ibkr_gun
    snapshot_date: str
    snapshot_time: str
    total_portfolio_lots: int = 0
    total_portfolio_value: float = 0.0
    symbols: Dict[str, SymbolIntraday] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'mode': self.mode,
            'snapshot_date': self.snapshot_date,
            'snapshot_time': self.snapshot_time,
            'total_portfolio_lots': self.total_portfolio_lots,
            'total_portfolio_value': self.total_portfolio_value,
            'symbol_count': len(self.symbols),
            'symbols': {s: data.to_dict() for s, data in self.symbols.items()}
        }


# ============================================================================
# Core Functions
# ============================================================================

def round_to_100(value: float) -> int:
    """
    Round to nearest 100.
    
    Examples:
        375 → 400
        350 → 400
        349 → 300
        250 → 300
    """
    return int(round(value / 100) * 100)


def round_down_to_100(value: float) -> int:
    """
    Round DOWN to nearest 100 (floor).
    
    Examples:
        375 → 300
        450 → 400
        500 → 500
    """
    return int(value // 100) * 100


def get_portfolio_rule(portfolio_pct: float) -> Dict[str, Any]:
    """
    Get applicable portfolio rule based on position's portfolio percentage.
    
    Args:
        portfolio_pct: Position's percentage of total portfolio (e.g., 5.5 for 5.5%)
        
    Returns:
        Rule dict with multiplier and description
    """
    for rule in PORTFOLIO_RULES:
        if portfolio_pct < rule['max_pct']:
            return rule
    return PORTFOLIO_RULES[-1]  # Last rule for >= 10%


def calculate_daily_add_limit(
    maxalw: int,
    portfolio_pct: float,
    min_lot: int = MIN_LOT_SIZE
) -> Tuple[int, str]:
    """
    Calculate maximum lot that can be added today for a symbol.
    
    Formula: MAXALW × multiplier, rounded to 100, minimum MIN_LOT_SIZE
    
    Args:
        maxalw: Symbol's MAXALW value
        portfolio_pct: Current portfolio percentage
        min_lot: Minimum lot size
        
    Returns:
        (add_limit, rule_description)
    """
    if maxalw <= 0:
        return 0, "NO_MAXALW"
    
    rule = get_portfolio_rule(portfolio_pct)
    raw_limit = maxalw * rule['multiplier']
    rounded_limit = round_to_100(raw_limit)
    
    # Enforce minimum
    if rounded_limit < min_lot:
        rounded_limit = min_lot
    
    return rounded_limit, f"{rule['description']} ({rule['max_pct']}%: {rule['multiplier']}x)"


def can_add_position(
    symbol: str,
    requested_lot: int,
    intraday: SymbolIntraday
) -> Tuple[bool, int, str]:
    """
    Check if position can be added based on daily limits.
    
    Args:
        symbol: Symbol string
        requested_lot: Requested lot to add
        intraday: Current intraday state for symbol
        
    Returns:
        (can_add, allowed_lot, reason)
    """
    # No MAXALW → no limit info
    if intraday.maxalw <= 0:
        return True, requested_lot, "NO_MAXALW_INFO"
    
    # Check remaining capacity
    remaining = intraday.todays_add_remaining
    
    if remaining <= 0:
        return False, 0, f"DAILY_LIMIT_REACHED (limit={intraday.todays_add_limit}, used={intraday.todays_add_used})"
    
    if requested_lot <= remaining:
        return True, requested_lot, "OK"
    
    # Partial fill allowed
    allowed = round_down_to_100(remaining)
    if allowed < MIN_LOT_SIZE:
        return False, 0, f"REMAINING_BELOW_MIN (remaining={remaining}, min={MIN_LOT_SIZE})"
    
    return True, allowed, f"PARTIAL_FILL (requested={requested_lot}, allowed={allowed})"


# ============================================================================
# IntraCon Engine
# ============================================================================

class IntraConEngine:
    """
    Intraday Controller Engine
    
    Manages daily position change limits based on BEFDAY snapshot and portfolio rules.
    """
    
    def __init__(self, output_dir: Optional[str] = None):
        self.output_dir = output_dir or os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self._snapshots: Dict[str, IntraConSnapshot] = {}  # mode -> snapshot
        self._initialized = False
        
    def initialize(
        self,
        mode: str,
        befday_positions: List[Dict[str, Any]],
        current_positions: List[Dict[str, Any]],
        static_data: Dict[str, Dict[str, Any]],
        pending_orders: Optional[List[Dict[str, Any]]] = None,
        total_portfolio_value: float = 0.0
    ) -> IntraConSnapshot:
        """
        Initialize IntraCon for a trading mode.
        
        Args:
            mode: Trading mode (hampro, ibkr_ped, ibkr_gun)
            befday_positions: Positions from start of day (BEFDAY snapshot)
            current_positions: Current live positions
            static_data: Static data dict with MAXALW values
            pending_orders: Open orders (to calculate potential positions)
            total_portfolio_value: Total portfolio value in USD
            
        Returns:
            IntraConSnapshot with calculated limits
        """
        now = datetime.now()
        snapshot = IntraConSnapshot(
            mode=mode,
            snapshot_date=now.strftime('%Y-%m-%d'),
            snapshot_time=now.isoformat(),
            total_portfolio_value=total_portfolio_value
        )
        
        # Build befday map
        befday_map: Dict[str, Dict[str, Any]] = {}
        for pos in befday_positions:
            symbol = pos.get('symbol') or pos.get('Symbol')
            if symbol:
                qty = pos.get('quantity') or pos.get('Quantity', 0)
                avg_cost = pos.get('avg_cost') or pos.get('Avg_Cost', 0)
                pos_type = pos.get('position_type') or pos.get('Position_Type', 'LONG')
                if pos_type == 'SHORT':
                    qty = -abs(qty)
                befday_map[symbol] = {
                    'qty': int(qty),
                    'avg_cost': float(avg_cost)
                }
        
        # Build current map
        current_map: Dict[str, Dict[str, Any]] = {}
        for pos in current_positions:
            symbol = pos.get('symbol') or pos.get('Symbol')
            if symbol:
                qty = pos.get('qty') or pos.get('quantity', 0)
                avg_cost = pos.get('avg_cost') or pos.get('avg_price', 0)
                current_price = pos.get('current_price') or pos.get('last_price', avg_cost)
                current_map[symbol] = {
                    'qty': int(qty),
                    'avg_cost': float(avg_cost),
                    'current_price': float(current_price)
                }
        
        # Build pending orders map (symbol -> {buy_qty, sell_qty})
        pending_map: Dict[str, Dict[str, int]] = {}
        if pending_orders:
            for order in pending_orders:
                symbol = order.get('symbol') or order.get('Symbol')
                if not symbol:
                    continue
                side = order.get('side', '').upper()
                remaining = order.get('remaining_qty') or order.get('remaining', 0)
                try:
                    remaining = int(abs(remaining))
                except:
                    continue
                    
                if symbol not in pending_map:
                    pending_map[symbol] = {'buy': 0, 'sell': 0}
                
                if side in ('BUY', 'B', 'LONG'):
                    pending_map[symbol]['buy'] += remaining
                elif side in ('SELL', 'S', 'SHORT', 'SSHORT'):
                    pending_map[symbol]['sell'] += remaining
        
        # Calculate total portfolio lots (absolute)
        total_lots = sum(abs(p.get('qty', 0)) for p in current_map.values())
        snapshot.total_portfolio_lots = total_lots
        
        # Calculate total potential lots (for potential_pct calculation)
        total_potential_lots = total_lots
        for symbol, pending in pending_map.items():
            # Net effect: buys add, sells subtract (in terms of absolute)
            cur_qty = current_map.get(symbol, {}).get('qty', 0)
            potential_qty = cur_qty + pending['buy'] - pending['sell']
            total_potential_lots += abs(potential_qty) - abs(cur_qty)
        
        # Combine all symbols
        all_symbols = set(befday_map.keys()) | set(current_map.keys()) | set(pending_map.keys())
        
        for symbol in all_symbols:
            bef = befday_map.get(symbol, {'qty': 0, 'avg_cost': 0})
            cur = current_map.get(symbol, {'qty': 0, 'avg_cost': 0, 'current_price': 0})
            pending = pending_map.get(symbol, {'buy': 0, 'sell': 0})
            static = static_data.get(symbol, {})
            
            # Get MAXALW (handle various formats)
            maxalw = static.get('MAXALW') or static.get('maxalw') or static.get('max_allowed', 0)
            try:
                maxalw = int(maxalw)
            except (ValueError, TypeError):
                maxalw = 0
            
            # Calculate portfolio percentage
            current_qty = int(cur['qty'])
            current_qty_abs = abs(current_qty)
            portfolio_pct = (current_qty_abs / total_lots * 100) if total_lots > 0 else 0
            
            # Calculate potential qty (current + pending buys - pending sells)
            pending_buy_qty = pending['buy']
            pending_sell_qty = pending['sell']
            potential_qty = current_qty + pending_buy_qty - pending_sell_qty
            potential_qty_abs = abs(potential_qty)
            potential_pct = (potential_qty_abs / total_potential_lots * 100) if total_potential_lots > 0 else 0
            
            # MAXALW validation
            maxalw_exceeded = current_qty_abs >= maxalw if maxalw > 0 else False
            potential_exceeds_maxalw = potential_qty_abs > maxalw if maxalw > 0 else False
            maxalw_headroom = maxalw - current_qty_abs if maxalw > 0 else 0
            potential_maxalw_headroom = maxalw - potential_qty_abs if maxalw > 0 else 0
            
            # Calculate daily add limit
            add_limit, rule_desc = calculate_daily_add_limit(maxalw, portfolio_pct)
            
            # Calculate todays_qty_chg
            todays_qty_chg = current_qty - bef['qty']
            
            # Calculate how much of the limit has been used (only positive changes count)
            todays_add_used = max(0, todays_qty_chg)
            todays_add_remaining = max(0, add_limit - todays_add_used)
            
            intraday = SymbolIntraday(
                symbol=symbol,
                maxalw=maxalw,
                befday_qty=bef['qty'],
                befday_avg_cost=bef['avg_cost'],
                current_qty=current_qty,
                current_avg_cost=cur['avg_cost'],
                current_price=cur['current_price'],
                pending_buy_qty=pending_buy_qty,
                pending_sell_qty=pending_sell_qty,
                potential_qty=potential_qty,
                potential_pct=potential_pct,
                todays_qty_chg=todays_qty_chg,
                todays_add_limit=add_limit,
                todays_add_used=todays_add_used,
                todays_add_remaining=todays_add_remaining,
                portfolio_pct=portfolio_pct,
                applicable_rule=rule_desc,
                maxalw_exceeded=maxalw_exceeded,
                potential_exceeds_maxalw=potential_exceeds_maxalw,
                maxalw_headroom=maxalw_headroom,
                potential_maxalw_headroom=potential_maxalw_headroom
            )
            
            snapshot.symbols[symbol] = intraday
        
        self._snapshots[mode] = snapshot
        self._initialized = True
        
        logger.info(
            f"[INTRACON] Initialized for {mode}: "
            f"{len(snapshot.symbols)} symbols, "
            f"total_lots={total_lots}, pending_orders={len(pending_orders or [])}"
        )
        
        return snapshot
    
    def get_snapshot(self, mode: str) -> Optional[IntraConSnapshot]:
        """Get current IntraCon snapshot for a mode"""
        return self._snapshots.get(mode)
    
    def get_symbol_state(self, symbol: str, mode: str) -> Optional[SymbolIntraday]:
        """Get intraday state for a specific symbol"""
        snapshot = self._snapshots.get(mode)
        if snapshot:
            return snapshot.symbols.get(symbol)
        return None
    
    def check_add_position(
        self,
        symbol: str,
        requested_lot: int,
        mode: str
    ) -> Tuple[bool, int, str]:
        """
        Check if position add is allowed.
        
        Checks:
        1. MAXALW limit (current + requested cannot exceed MAXALW)
        2. Daily add limit from portfolio % rules
        3. Minimum lot size
        
        Args:
            symbol: Symbol to add
            requested_lot: Requested lot to add
            mode: Trading mode
            
        Returns:
            (allowed, adjusted_lot, reason)
        """
        intraday = self.get_symbol_state(symbol, mode)
        
        if not intraday:
            # No state → allow but warn
            logger.warning(f"[INTRACON] No state for {symbol}, allowing with warning")
            return True, round_to_100(requested_lot), "NO_INTRACON_STATE"
        
        # Round requested lot first
        requested_lot = round_to_100(requested_lot)
        if requested_lot < MIN_LOT_SIZE:
            return False, 0, f"BELOW_MIN_LOT (requested={requested_lot}, min={MIN_LOT_SIZE})"
        
        # CHECK 1: MAXALW exceeded?
        if intraday.maxalw > 0:
            # Current already at or above MAXALW
            if intraday.maxalw_exceeded:
                return False, 0, f"MAXALW_EXCEEDED (current={abs(intraday.current_qty)}, maxalw={intraday.maxalw})"
            
            # Would adding exceed MAXALW?
            new_total = abs(intraday.current_qty) + requested_lot
            if new_total > intraday.maxalw:
                # Cap to available headroom
                available = intraday.maxalw_headroom
                capped = round_down_to_100(available)
                if capped < MIN_LOT_SIZE:
                    return False, 0, f"MAXALW_WOULD_EXCEED (headroom={available}, min={MIN_LOT_SIZE})"
                logger.info(f"[INTRACON] {symbol} capped from {requested_lot} to {capped} due to MAXALW")
                requested_lot = capped
        
        # CHECK 2: Daily add limit from portfolio % rules
        return can_add_position(symbol, requested_lot, intraday)
    
    def record_add(self, symbol: str, lot: int, mode: str) -> bool:
        """
        Record that a position add was executed.
        Updates todays_add_used and todays_add_remaining.
        
        Args:
            symbol: Symbol added
            lot: Lot amount added
            mode: Trading mode
            
        Returns:
            Success
        """
        snapshot = self._snapshots.get(mode)
        if not snapshot:
            return False
        
        intraday = snapshot.symbols.get(symbol)
        if not intraday:
            # Create new entry
            intraday = SymbolIntraday(symbol=symbol)
            snapshot.symbols[symbol] = intraday
        
        intraday.todays_add_used += lot
        intraday.todays_add_remaining = max(0, intraday.todays_add_limit - intraday.todays_add_used)
        intraday.current_qty += lot
        intraday.todays_qty_chg = intraday.current_qty - intraday.befday_qty
        
        logger.info(
            f"[INTRACON] Recorded add: {symbol} +{lot} lot, "
            f"used={intraday.todays_add_used}/{intraday.todays_add_limit}"
        )
        
        return True
    
    def get_all_symbols_summary(self, mode: str) -> List[Dict[str, Any]]:
        """
        Get summary of all symbols for display.
        """
        snapshot = self._snapshots.get(mode)
        if not snapshot:
            return []
        
        result = []
        for symbol, intraday in sorted(snapshot.symbols.items()):
            result.append(intraday.to_dict())
        
        return result
    
    def save_snapshot(self, mode: str, filepath: Optional[str] = None) -> bool:
        """Save snapshot to JSON file"""
        snapshot = self._snapshots.get(mode)
        if not snapshot:
            return False
        
        if not filepath:
            today = date.today().strftime('%Y%m%d')
            filepath = os.path.join(self.output_dir, 'intracon', f'intracon_{mode}_{today}.json')
        
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(snapshot.to_dict(), f, indent=2, ensure_ascii=False)
        
        logger.info(f"[INTRACON] Saved snapshot to {filepath}")
        return True


# ============================================================================
# Global Instance
# ============================================================================

_intracon_engine: Optional[IntraConEngine] = None


def get_intracon_engine() -> Optional[IntraConEngine]:
    """Get global IntraCon engine instance"""
    return _intracon_engine


def initialize_intracon_engine(output_dir: Optional[str] = None) -> IntraConEngine:
    """Initialize global IntraCon engine"""
    global _intracon_engine
    _intracon_engine = IntraConEngine(output_dir=output_dir)
    logger.info("[INTRACON] Engine initialized")
    return _intracon_engine
