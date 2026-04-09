"""
OrderLifecycleTracker — Deterministic Order Monitoring Engine
=============================================================

Gönderilen HER emri fill alana veya cancel olana kadar izler.
Fill sonrasi pozisyonu TP çıkışına kadar takip eder.
LLM kullanmaz — tamamen kural tabanlı, her 30sn cycle.

Her hesap (HAMPRO, IBKR_PED) ayrı state ile izlenir.

Data Sources (per account):
  - psfalgo:positions:{account}          → current positions (qty, befday_qty)
  - psfalgo:befday:positions:{account}   → befday positions
  - psfalgo:exposure:{account}           → exposure (pot_total, pot_max, pct)
  - psfalgo:open_orders:{account}        → open orders
  - psfalgo:todays_fills:{account}       → today's fills
  - tt:ticks:{symbol}                    → truth tick history
  - ETF:PFF live data                    → PFF health monitoring

Output:
  - Structured logs every 30s
  - Redis: psfalgo:tracker:snapshot:{account}  → for QAgent
  - Redis: psfalgo:tracker:alerts              → urgent alerts

Usage:
    tracker = OrderLifecycleTracker()
    tracker.on_order_sent(order_data, account_id, market_snap)
    tracker.on_fill(fill_data, account_id, market_snap)
    tracker.check_cycle()  # call every 30s from RUNALL
"""

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from app.core.logger import logger


# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

CHECK_INTERVAL_SEC = 30          # How often check_cycle runs
MIN_PROFIT_CENTS = 6             # Minimum profit target (6 cents)
PFF_CAUTION_THRESHOLD = -0.04    # PFF drop to enter CAUTION (bad for longs)
PFF_BEARISH_THRESHOLD = -0.08    # PFF drop to enter BEARISH (bad for longs)
PFF_BULL_CAUTION_THRESHOLD = 0.04   # PFF rise to enter BULL_CAUTION (bad for shorts)
PFF_BULLISH_THRESHOLD = 0.08        # PFF rise to enter BULLISH (bad for shorts)
STALE_ORDER_MINUTES = 10         # Order older than this = STALE
MAX_TRACKED_ORDERS = 200         # Cap to prevent memory bloat
LOG_PREFIX = "[TRACKER]"


# ═══════════════════════════════════════════════════════════════
# TRACKED ORDER
# ═══════════════════════════════════════════════════════════════

@dataclass
class TrackedOrder:
    """
    Represents a single order from creation through fill to exit.
    Records market conditions at every stage.
    """
    # ── Identity ──
    order_id: str = ''
    symbol: str = ''
    action: str = ''              # BUY, SELL
    price: float = 0.0            # order price
    lot: int = 0
    tag: str = ''                 # MM_NEWC_LONG_INC, etc.
    engine: str = ''              # NEWC, MM, LT_TRIM, KARBOTU, PATADD, ADDNEWPOS, REV
    account_id: str = ''          # HAMPRO, IBKR_PED

    # ── Creation snapshot ──
    created_ts: float = 0.0
    bid_at_create: float = 0.0
    ask_at_create: float = 0.0
    spread_at_create: float = 0.0
    pff_at_create: float = 0.0
    truth_tick_at_create: float = 0.0
    truth_tick_venue_at_create: str = ''
    truth_ticks_at_create: List[Dict[str, Any]] = field(default_factory=list)  # last 5 ticks at order time

    # ── Live monitoring (updated each cycle) ──
    last_check_ts: float = 0.0
    current_bid: float = 0.0
    current_ask: float = 0.0
    current_spread: float = 0.0
    current_pff: float = 0.0
    current_truth_tick: float = 0.0
    pff_delta_from_create: float = 0.0   # PFF now - PFF at create
    price_distance_cents: float = 0.0     # how far from fill

    # ── Status ──
    status: str = 'OPEN'          # OPEN → FILLED → TP_PENDING → CLOSED / OV / CANCELLED
    fill_price: float = 0.0
    fill_ts: float = 0.0
    bid_at_fill: float = 0.0
    ask_at_fill: float = 0.0
    spread_at_fill: float = 0.0
    pff_at_fill: float = 0.0
    truth_tick_at_fill: float = 0.0
    truth_ticks_at_fill: List[Dict[str, Any]] = field(default_factory=list)  # last 5 ticks at fill time
    pff_delta_from_fill: float = 0.0     # PFF now - PFF at fill

    # ── Per-Order PFF Tracking (cents) ──
    pff_sent_to_fill_c: float = 0.0      # (PFF@Fill - PFF@Sent) * 100 in cents
    pff_fill_to_now_c: float = 0.0       # (PFF@Now - PFF@Fill) * 100 in cents
    pff_sent_to_now_c: float = 0.0       # (PFF@Now - PFF@Sent) * 100 in cents
    pff_order_state: str = 'NORMAL'      # Per-order PFF state: NORMAL/CAUTION/BEARISH/BULL_CAUTION/BULLISH

    # ── Exit tracking ──
    exit_price: float = 0.0
    exit_ts: float = 0.0
    exit_pnl_cents: float = 0.0
    exit_strategy: str = ''       # NORMAL_TP, TRUTH_FRONTRUN, AGRESIF_EXIT, L2_EXIT, OV

    # ── Analysis ──
    check_count: int = 0          # how many times we've checked this order
    max_favorable_cents: float = 0.0   # best point (BUY: lowest truth tick drop)
    max_adverse_cents: float = 0.0     # worst point
    fill_probability: str = ''    # LIKELY, WAITING, UNLIKELY, STALE
    venue_hints: List[str] = field(default_factory=list)
    analysis_notes: List[str] = field(default_factory=list)


@dataclass
class SymbolCostBasis:
    """
    Per-symbol daily cost basis tracking.
    Maintains running weighted average for buys and sells.
    
    Example:
        Fill 1: BUY 200 @ 18.76 → avg_buy=18.76, buy_qty=200
        Fill 2: BUY 100 @ 18.80 → avg_buy=18.773, buy_qty=300
        Fill 3: SELL 150 @ 18.85 → avg_sell=18.85, sell_qty=150
        → net_qty=150 (long), realized_pnl = 150 * (18.85 - 18.773) = +$11.55
    """
    symbol: str = ''
    
    # Buy side
    buy_qty: int = 0
    buy_total_cost: float = 0.0      # sum of (qty * price) for all buys
    buy_fill_count: int = 0
    
    # Sell side
    sell_qty: int = 0
    sell_total_proceeds: float = 0.0  # sum of (qty * price) for all sells
    sell_fill_count: int = 0
    
    # Fill history (compact)
    fills: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def avg_buy_cost(self) -> float:
        """Weighted average buy price."""
        return round(self.buy_total_cost / self.buy_qty, 4) if self.buy_qty > 0 else 0.0
    
    @property
    def avg_sell_cost(self) -> float:
        """Weighted average sell price."""
        return round(self.sell_total_proceeds / self.sell_qty, 4) if self.sell_qty > 0 else 0.0
    
    @property
    def net_qty(self) -> int:
        """Net position: positive = long, negative = short."""
        return self.buy_qty - self.sell_qty
    
    @property
    def realized_pnl(self) -> float:
        """
        Realized PnL from matched buy/sell pairs.
        Uses FIFO: matched_qty * (avg_sell - avg_buy)
        """
        matched = min(self.buy_qty, self.sell_qty)
        if matched <= 0 or self.avg_buy_cost <= 0 or self.avg_sell_cost <= 0:
            return 0.0
        return round(matched * (self.avg_sell_cost - self.avg_buy_cost), 2)
    
    @property
    def realized_pnl_cents_per_share(self) -> float:
        """Realized PnL in cents per matched share."""
        matched = min(self.buy_qty, self.sell_qty)
        if matched <= 0:
            return 0.0
        return round((self.avg_sell_cost - self.avg_buy_cost) * 100, 1)
    
    def add_fill(self, action: str, qty: int, price: float, tag: str = '', ts: float = 0):
        """Record a fill and update running averages."""
        qty = abs(qty)
        if action.upper() == 'BUY':
            self.buy_total_cost += qty * price
            self.buy_qty += qty
            self.buy_fill_count += 1
        elif action.upper() in ('SELL', 'SHORT'):
            self.sell_total_proceeds += qty * price
            self.sell_qty += qty
            self.sell_fill_count += 1
        
        self.fills.append({
            'act': action.upper()[:1],  # B or S
            'q': qty,
            'p': round(price, 2),
            'tag': tag[:20] if tag else '',
            't': round(ts) if ts else 0,
        })
        # Cap fill history
        if len(self.fills) > 50:
            self.fills = self.fills[-50:]
    
    def to_compact(self) -> Dict[str, Any]:
        """Compact dict for logging/Redis."""
        return {
            's': self.symbol,
            'buy_q': self.buy_qty,
            'avg_buy': self.avg_buy_cost,
            'buy_n': self.buy_fill_count,
            'sell_q': self.sell_qty,
            'avg_sell': self.avg_sell_cost,
            'sell_n': self.sell_fill_count,
            'net': self.net_qty,
            'rpnl': self.realized_pnl,
            'rpnl_c': self.realized_pnl_cents_per_share,
        }


def _detect_engine(tag: str) -> str:
    """Detect engine from order tag."""
    t = (tag or '').upper()
    if 'NEWC' in t:
        return 'NEWC'
    if 'KARBOTU' in t or 'KBOT' in t:
        return 'KARBOTU'
    if 'PATADD' in t or 'PAT_' in t:
        return 'PATADD'
    if 'LT_TRIM' in t or 'LTTRIM' in t or 'LT_' in t:
        return 'LT_TRIM'
    if 'ADDNEW' in t or 'ANP' in t:
        return 'ADDNEWPOS'
    if 'REV' in t:
        return 'REV'
    if 'MM' in t:
        return 'MM'
    return 'UNKNOWN'


# ═══════════════════════════════════════════════════════════════
# PFF HEALTH STATE MACHINE
# ═══════════════════════════════════════════════════════════════

class PFFHealthMonitor:
    """
    Track PFF ETF price and determine market health state.
    Bidirectional: tracks both drops (bad for longs) and rises (bad for shorts).

    Bear States (for LONG/BUY positions — PFF dropping):
      NORMAL       → PFF stable
      CAUTION      → PFF dropping, tighten TP targets for longs
      BEARISH      → PFF crashed, aggressive exit longs

    Bull States (for SHORT/SELL positions — PFF rising):
      NORMAL       → PFF stable
      BULL_CAUTION → PFF rising, tighten TP targets for shorts
      BULLISH      → PFF surging, aggressive exit shorts
    """

    def __init__(self):
        self._price_history: List[Tuple[float, float]] = []  # (ts, price)
        self._bear_state: str = 'NORMAL'   # for longs — PFF dropping
        self._bull_state: str = 'NORMAL'   # for shorts — PFF rising
        self._anchor_price: float = 0.0    # reference price (set at market open)
        self._last_price: float = 0.0
        self._delta_from_anchor: float = 0.0
        self._delta_5min: float = 0.0

    @property
    def state(self) -> str:
        """Legacy: returns bear_state for backward compatibility."""
        return self._bear_state

    @property
    def bear_state(self) -> str:
        """State for LONG/BUY positions (PFF dropping = bad)."""
        return self._bear_state

    @property
    def bull_state(self) -> str:
        """State for SHORT/SELL positions (PFF rising = bad)."""
        return self._bull_state

    @property
    def last_price(self) -> float:
        return self._last_price

    def state_for_action(self, action: str) -> str:
        """
        Get the relevant PFF state for an order action.
        BUY  → bear_state (PFF dropping is bad)
        SELL → bull_state (PFF rising is bad)
        """
        if action.upper() in ('SELL', 'SHORT', 'S'):
            return self._bull_state
        return self._bear_state

    def update(self, pff_price: float) -> str:
        """Update PFF price and return bear_state (legacy compat)."""
        if pff_price <= 0:
            return self._bear_state

        now = time.time()
        self._last_price = pff_price

        # Set anchor on first price
        if self._anchor_price <= 0:
            self._anchor_price = pff_price

        # Keep last 120 prices (~1 hour at 30s interval)
        self._price_history.append((now, pff_price))
        if len(self._price_history) > 120:
            self._price_history = self._price_history[-120:]

        # Calculate deltas
        self._delta_from_anchor = pff_price - self._anchor_price

        # 5-minute delta (last 10 entries at 30s interval)
        self._delta_5min = 0
        if len(self._price_history) >= 10:
            self._delta_5min = pff_price - self._price_history[-10][1]

        # ── BEAR STATE (for longs — PFF dropping) ──
        old_bear = self._bear_state
        if self._delta_from_anchor <= PFF_BEARISH_THRESHOLD:
            self._bear_state = 'BEARISH'
        elif self._delta_from_anchor <= PFF_CAUTION_THRESHOLD:
            self._bear_state = 'CAUTION'
        else:
            self._bear_state = 'NORMAL'

        if self._bear_state != old_bear:
            logger.warning(
                f"{LOG_PREFIX} PFF BEAR STATE: {old_bear} → {self._bear_state} | "
                f"PFF=${pff_price:.2f} anchor=${self._anchor_price:.2f} "
                f"delta=${self._delta_from_anchor:+.3f} 5m_delta=${self._delta_5min:+.3f}"
            )

        # ── BULL STATE (for shorts — PFF rising) ──
        old_bull = self._bull_state
        if self._delta_from_anchor >= PFF_BULLISH_THRESHOLD:
            self._bull_state = 'BULLISH'
        elif self._delta_from_anchor >= PFF_BULL_CAUTION_THRESHOLD:
            self._bull_state = 'BULL_CAUTION'
        else:
            self._bull_state = 'NORMAL'

        if self._bull_state != old_bull:
            logger.warning(
                f"{LOG_PREFIX} PFF BULL STATE: {old_bull} → {self._bull_state} | "
                f"PFF=${pff_price:.2f} anchor=${self._anchor_price:.2f} "
                f"delta=${self._delta_from_anchor:+.3f} 5m_delta=${self._delta_5min:+.3f}"
            )

        return self._bear_state

    def get_delta_from(self, ref_price: float) -> float:
        """Get PFF delta from a reference price."""
        if ref_price <= 0 or self._last_price <= 0:
            return 0.0
        return round(self._last_price - ref_price, 4)

    def reset_anchor(self, price: float = 0):
        """Reset anchor (call at market open)."""
        self._anchor_price = price if price > 0 else self._last_price
        self._bear_state = 'NORMAL'
        self._bull_state = 'NORMAL'
        self._delta_from_anchor = 0.0
        self._delta_5min = 0.0
        self._price_history.clear()


# ═══════════════════════════════════════════════════════════════
# ACCOUNT STATE
# ═══════════════════════════════════════════════════════════════

@dataclass
class AccountState:
    """Per-account tracking state."""
    account_id: str = ''
    tracked_orders: Dict[str, TrackedOrder] = field(default_factory=dict)  # key = order_id or symbol:action

    # Daily counters
    total_orders_sent: int = 0
    total_fills: int = 0
    total_exits: int = 0
    total_pnl_cents: float = 0.0
    wins: int = 0
    losses: int = 0
    cancelled: int = 0

    # Engine breakdown
    engine_orders: Dict[str, int] = field(default_factory=dict)
    engine_fills: Dict[str, int] = field(default_factory=dict)
    engine_pnl: Dict[str, List[float]] = field(default_factory=dict)

    # Per-symbol cost basis (key = symbol)
    symbol_costs: Dict[str, SymbolCostBasis] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# MAIN TRACKER
# ═══════════════════════════════════════════════════════════════

class OrderLifecycleTracker:
    """
    Deterministic rule-based order monitoring engine.

    Tracks every order from creation → fill → exit.
    Runs every 30s, no LLM, $0 cost.
    Account-isolated: HAMPRO and IBKR_PED are tracked separately.
    """

    def __init__(self):
        self._accounts: Dict[str, AccountState] = {}
        self._pff_monitor = PFFHealthMonitor()
        self._last_check_ts: float = 0
        self._redis = None
        self._cycle_count: int = 0
        self._eod_triggered: bool = False
        logger.info(
            f"{LOG_PREFIX} OrderLifecycleTracker initialized | "
            f"interval={CHECK_INTERVAL_SEC}s min_profit={MIN_PROFIT_CENTS}c "
            f"PFF thresholds: caution={PFF_CAUTION_THRESHOLD} bearish={PFF_BEARISH_THRESHOLD}"
        )

    def _get_account(self, account_id: str) -> AccountState:
        """Get or create per-account state."""
        if account_id not in self._accounts:
            self._accounts[account_id] = AccountState(account_id=account_id)
            logger.info(f"{LOG_PREFIX} Account state created: {account_id}")
        return self._accounts[account_id]

    def _get_redis(self):
        """Lazy Redis connection."""
        if self._redis is None:
            try:
                from app.core.redis_client import get_redis_client
                client = get_redis_client()
                self._redis = getattr(client, 'sync', client)
            except Exception:
                import redis
                self._redis = redis.Redis(host='localhost', port=6379, db=0)
        return self._redis

    def _get_pff_price(self) -> float:
        """Get current PFF ETF price."""
        try:
            r = self._get_redis()
            raw = r.get("tt:ticks:PFF")
            if raw:
                ticks = json.loads(raw)
                if ticks and isinstance(ticks, list):
                    return float(ticks[-1].get('price', 0))
        except Exception:
            pass

        # Fallback: DataFabric
        try:
            from app.core.data_fabric import DataFabric
            fb = DataFabric()
            live = fb.get_etf_live("PFF")
            if live:
                return float(live.get('last', 0) or 0)
        except Exception:
            pass
        return 0.0

    def _get_truth_tick(self, symbol: str) -> Tuple[float, str]:
        """Get latest truth tick price and venue for a symbol.
        ⚠️ STALENESS CHECK: Rejects ticks older than 24 hours.
        """
        try:
            import time as _time_tt
            r = self._get_redis()
            raw = r.get(f"tt:ticks:{symbol}")
            if raw:
                ticks = json.loads(raw)
                if ticks and isinstance(ticks, list):
                    now = _time_tt.time()
                    STALENESS_LIMIT = 86400  # 24 hours
                    # Iterate from newest to oldest
                    for tick in reversed(ticks):
                        tick_ts = tick.get('ts', 0)
                        if tick_ts > 0 and (now - tick_ts) > STALENESS_LIMIT:
                            continue  # STALE — skip
                        price = float(tick.get('price', 0))
                        if price > 0:
                            return (
                                price,
                                tick.get('exch', tick.get('venue', ''))
                            )
                    # All ticks are stale
                    return (0.0, '')
        except Exception:
            pass
        return (0.0, '')

    def _get_last_n_truth_ticks(self, symbol: str, n: int = 5) -> List[Dict[str, Any]]:
        """Get last N truth ticks as compact dicts: [{p: price, v: venue, ts: timestamp}, ...]"""
        try:
            r = self._get_redis()
            raw = r.get(f"tt:ticks:{symbol}")
            if not raw:
                return []
            ticks = json.loads(raw)
            if not ticks or not isinstance(ticks, list):
                return []
            result = []
            for tick in reversed(ticks):  # newest first
                price = float(tick.get('price', 0))
                if price > 0:
                    result.append({
                        'p': round(price, 4),
                        'v': tick.get('exch', tick.get('venue', '')),
                        'ts': tick.get('ts', 0),
                    })
                if len(result) >= n:
                    break
            return result
        except Exception:
            return []

    def _get_truth_tick_trend(self, symbol: str, lookback: int = 10) -> Dict[str, Any]:
        """
        Analyze truth tick trend for a symbol.
        
        Returns:
            {
                'prices': [18.75, 18.73, ...],   # newest first
                'trend': 'FALLING' | 'RISING' | 'FLAT',
                'velocity': -0.003,               # price change per tick (negative = falling)
                'range_cents': 4.0,               # high-low in cents
                'latest': 18.73,
                'venues': {'EDGA': 4, 'ARCA': 2}, # venue distribution
                'dominant_venue': 'EDGA',
                'tick_count': 6,
            }
        """
        result = {
            'prices': [], 'trend': 'UNKNOWN', 'velocity': 0.0,
            'range_cents': 0.0, 'latest': 0.0, 'venues': {},
            'dominant_venue': '', 'tick_count': 0,
        }
        try:
            r = self._get_redis()
            raw = r.get(f"tt:ticks:{symbol}")
            if not raw:
                return result
            ticks = json.loads(raw)
            if not ticks or not isinstance(ticks, list):
                return result

            # Filter valid ticks (last 2 hours — illiquid prefs trade rarely)
            now = time.time()
            valid = []
            for tick in reversed(ticks):  # newest first
                ts = tick.get('ts', 0)
                if ts > 0 and (now - ts) > 7200:  # 2 hour cutoff (was 5min — too short for illiquid)
                    continue
                price = float(tick.get('price', 0))
                if price > 0:
                    venue = tick.get('exch', tick.get('venue', ''))
                    valid.append({'price': price, 'venue': venue, 'ts': ts})
                if len(valid) >= lookback:
                    break

            if not valid:
                return result

            prices = [t['price'] for t in valid]
            venues = {}
            for t in valid:
                v = t['venue'] or 'UNK'
                venues[v] = venues.get(v, 0) + 1

            result['prices'] = prices
            result['latest'] = prices[0]
            result['tick_count'] = len(prices)
            result['venues'] = venues
            result['dominant_venue'] = max(venues, key=venues.get) if venues else ''

            # Trend calculation
            if len(prices) >= 3:
                newest_avg = sum(prices[:3]) / 3
                oldest_avg = sum(prices[-3:]) / 3
                diff = newest_avg - oldest_avg
                result['velocity'] = round(diff / len(prices), 4)

                if diff > 0.015:
                    result['trend'] = 'RISING'
                elif diff < -0.015:
                    result['trend'] = 'FALLING'
                else:
                    result['trend'] = 'FLAT'
            elif len(prices) >= 2:
                diff = prices[0] - prices[-1]
                result['velocity'] = round(diff, 4)
                result['trend'] = 'RISING' if diff > 0.01 else ('FALLING' if diff < -0.01 else 'FLAT')

            result['range_cents'] = round((max(prices) - min(prices)) * 100, 1)

        except Exception:
            pass
        return result

    def _get_l1(self, symbol: str) -> Tuple[float, float]:
        """Get bid/ask for a symbol.
        
        🔑 TICKER CONVENTION: Tries both Hammer and PREF_IBKR formats.
        """
        try:
            from app.core.data_fabric import DataFabric
            from app.live.symbol_mapper import SymbolMapper
            
            fb = DataFabric()
            
            # Try all format variants
            hammer_sym = SymbolMapper.to_hammer_symbol(symbol)
            display_sym = SymbolMapper.to_display_symbol(symbol)
            for sym in dict.fromkeys([symbol, hammer_sym, display_sym]):
                snap = fb.get_fast_snapshot(sym)
                if snap:
                    bid = float(snap.get('bid', 0) or 0)
                    ask = float(snap.get('ask', 0) or 0)
                    if bid > 0 and ask > 0:
                        return (bid, ask)
        except Exception:
            pass
        return (0.0, 0.0)

    def _get_l2_asks(self, symbol: str) -> List[Tuple[float, int]]:
        """Get L2 ask stack: [(price, size), ...] sorted ascending."""
        try:
            r = self._get_redis()
            # Try DataFabric L2 key
            raw = r.get(f"l2:asks:{symbol}")
            if raw:
                data = json.loads(raw)
                if isinstance(data, list):
                    return [(float(x.get('price', 0)), int(x.get('size', 0)))
                            for x in data if float(x.get('price', 0)) > 0]
        except Exception:
            pass
        return []

    # ═══════════════════════════════════════════════════════════
    # EVENT HANDLERS
    # ═══════════════════════════════════════════════════════════

    def on_order_sent(
        self,
        symbol: str,
        action: str,
        price: float,
        lot: int,
        tag: str,
        account_id: str,
        order_id: str = '',
    ):
        """
        Called when an order is sent to broker.
        Records full market snapshot at order creation time.
        """
        # Normalize symbol to display format for consistent key matching
        try:
            from app.live.symbol_mapper import SymbolMapper
            symbol = SymbolMapper.to_display_symbol(symbol)
        except Exception:
            pass

        acct = self._get_account(account_id)
        engine = _detect_engine(tag)
        pff_price = self._get_pff_price()
        tt_price, tt_venue = self._get_truth_tick(symbol)
        bid, ask = self._get_l1(symbol)
        last5_ticks = self._get_last_n_truth_ticks(symbol, 5)

        key = order_id or f"{symbol}:{action}:{account_id}"

        tracked = TrackedOrder(
            order_id=key,
            symbol=symbol,
            action=action.upper(),
            price=price,
            lot=lot,
            tag=tag,
            engine=engine,
            account_id=account_id,
            created_ts=time.time(),
            bid_at_create=bid,
            ask_at_create=ask,
            spread_at_create=round(ask - bid, 4) if bid > 0 and ask > 0 else 0,
            pff_at_create=pff_price,
            truth_tick_at_create=tt_price,
            truth_tick_venue_at_create=tt_venue,
            truth_ticks_at_create=last5_ticks,
            status='OPEN',
        )

        acct.tracked_orders[key] = tracked
        acct.total_orders_sent += 1
        acct.engine_orders[engine] = acct.engine_orders.get(engine, 0) + 1

        # Cap tracked orders
        if len(acct.tracked_orders) > MAX_TRACKED_ORDERS:
            # Remove oldest closed orders
            closed = [k for k, v in acct.tracked_orders.items()
                      if v.status in ('CLOSED', 'OV', 'CANCELLED')]
            for k in closed[:50]:
                del acct.tracked_orders[k]

        # Format last 5 ticks for log
        ticks_str = ','.join([f"${t['p']:.2f}({t['v']})" for t in last5_ticks[:5]]) if last5_ticks else 'N/A'

        logger.info(
            f"{LOG_PREFIX} [{account_id}] ORDER SENT: {action} {symbol} "
            f"{lot}lot @${price:.2f} | engine={engine} tag={tag} | "
            f"bid=${bid:.2f} ask=${ask:.2f} spr={tracked.spread_at_create*100:.0f}c | "
            f"PFF=${pff_price:.2f} tt=${tt_price:.2f}({tt_venue}) | "
            f"last5tt=[{ticks_str}]"
        )

    def on_fill(
        self,
        symbol: str,
        action: str,
        fill_price: float,
        tag: str,
        account_id: str,
        order_id: str = '',
        fill_qty: int = 0,
    ):
        """
        Called when a fill event arrives from broker.
        Records fill price + market snapshot at fill time.
        """
        # Normalize symbol to display format (e.g., WBS-F → WBS PRF)
        # so that Redis lookups (tt:ticks:WBS PRF) and sent-order key matching work.
        try:
            from app.live.symbol_mapper import SymbolMapper
            symbol = SymbolMapper.to_display_symbol(symbol)
        except Exception:
            pass

        acct = self._get_account(account_id)
        engine = _detect_engine(tag)
        pff_price = self._get_pff_price()
        tt_price, tt_venue = self._get_truth_tick(symbol)
        bid, ask = self._get_l1(symbol)
        last5_ticks = self._get_last_n_truth_ticks(symbol, 5)

        key = order_id or f"{symbol}:{action.upper()}:{account_id}"
        tracked = acct.tracked_orders.get(key)

        # ═══ SMART SENT→FILL MATCHING ═══
        # Problem: on_order_sent stores with key = order_id (e.g., "33678")
        # but on_fill arrives without order_id → key = "VLYPO:SELL:IBKR_PED"
        # Also: chunked orders have keys like "33678", "33679" but fill comes as
        # "VLYPO:SELL:IBKR_PED" → no match → PFF@sent = $0.00
        #
        # Solution: Search all OPEN orders for same symbol+action, pick best match
        if not tracked:
            # Fallback 1: Try symbol:action:account key
            fallback_key = f"{symbol}:{action.upper()}:{account_id}"
            tracked = acct.tracked_orders.get(fallback_key)

        if not tracked:
            # Fallback 2: Search ALL open/unfilled tracked orders for same symbol+action
            best_match = None
            best_time = 0
            for _k, _v in acct.tracked_orders.items():
                if (_v.symbol == symbol
                    and _v.action == action.upper()
                    and _v.status == 'OPEN'
                    and _v.created_ts > best_time):
                    best_match = _v
                    best_time = _v.created_ts
            if best_match:
                tracked = best_match
                key = best_match.order_id

        if not tracked:
            # No matching sent order found — create new tracked order for this fill
            tracked = TrackedOrder(
                order_id=key,
                symbol=symbol,
                action=action.upper(),
                price=fill_price,
                lot=fill_qty,
                tag=tag,
                engine=engine,
                account_id=account_id,
                created_ts=time.time(),
            )
            acct.tracked_orders[key] = tracked

        tracked.status = 'FILLED'
        tracked.fill_price = fill_price
        tracked.fill_ts = time.time()
        tracked.bid_at_fill = bid
        tracked.ask_at_fill = ask
        tracked.spread_at_fill = round(ask - bid, 4) if bid > 0 and ask > 0 else 0
        tracked.pff_at_fill = pff_price
        tracked.truth_tick_at_fill = tt_price
        tracked.truth_ticks_at_fill = last5_ticks

        # ── PER-ORDER PFF SENT→FILL DELTA (cents) ──
        if tracked.pff_at_create > 0 and pff_price > 0:
            tracked.pff_sent_to_fill_c = round((pff_price - tracked.pff_at_create) * 100, 1)

        acct.total_fills += 1
        acct.engine_fills[engine] = acct.engine_fills.get(engine, 0) + 1

        # ── AVG COST UPDATE ──
        if symbol not in acct.symbol_costs:
            acct.symbol_costs[symbol] = SymbolCostBasis(symbol=symbol)
        cost_basis = acct.symbol_costs[symbol]
        # Use fill_qty if provided, else tracked.lot, else 1 as fallback
        actual_qty = fill_qty or tracked.lot or 1
        if fill_qty and tracked.lot == 0:
            tracked.lot = fill_qty  # Backfill lot info
        cost_basis.add_fill(action, actual_qty, fill_price, tag, time.time())

        # Analyze fill quality
        fill_vs_tt = round((fill_price - tt_price) * 100, 1) if tt_price > 0 else 0
        time_to_fill = round(tracked.fill_ts - tracked.created_ts, 1) if tracked.created_ts > 0 else 0

        # Format last 5 ticks for log
        ticks_str = ','.join([f"${t['p']:.2f}({t['v']})" for t in last5_ticks[:5]]) if last5_ticks else 'N/A'

        # Format ticks from order send time for comparison
        sent_ticks_str = ','.join([f"${t['p']:.2f}" for t in tracked.truth_ticks_at_create[:5]]) if tracked.truth_ticks_at_create else 'N/A'

        logger.warning(
            f"{LOG_PREFIX} [{account_id}] FILL: {action} {symbol} "
            f"{actual_qty}lot @${fill_price:.2f} | engine={engine} | "
            f"bid=${bid:.2f} ask=${ask:.2f} spr={tracked.spread_at_fill*100:.0f}c | "
            f"PFF=${pff_price:.2f} tt=${tt_price:.2f}({tt_venue}) | "
            f"fill_vs_tt={fill_vs_tt:+.0f}c time={time_to_fill:.0f}s | "
            f"PFF: @sent=${tracked.pff_at_create:.2f} @fill=${pff_price:.2f} "
            f"sent→fill={tracked.pff_sent_to_fill_c:+.1f}c | "
            f"AVG_COST: buy=${cost_basis.avg_buy_cost:.2f}({cost_basis.buy_qty}q) "
            f"sell=${cost_basis.avg_sell_cost:.2f}({cost_basis.sell_qty}q) "
            f"net={cost_basis.net_qty} rpnl={cost_basis.realized_pnl:+.2f} | "
            f"tt@fill=[{ticks_str}] tt@sent=[{sent_ticks_str}]"
        )

    def on_exit(
        self,
        symbol: str,
        action: str,
        exit_price: float,
        tag: str,
        account_id: str,
        strategy: str = '',
        order_id: str = '',
    ):
        """
        Called when an exit (profit-take or stop-loss) fills.
        Calculates final PnL and updates stats.
        """
        acct = self._get_account(account_id)

        # Find the matching tracked order
        # For an exit SELL, we look for the original BUY
        # For an exit BUY (cover short), we look for the original SELL
        original_action = 'BUY' if action.upper() in ('SELL',) else 'SELL'
        key = order_id or f"{symbol}:{original_action}:{account_id}"
        tracked = acct.tracked_orders.get(key)

        if not tracked or tracked.fill_price <= 0:
            logger.info(f"{LOG_PREFIX} [{account_id}] EXIT for untracked: {action} {symbol} @${exit_price:.2f}")
            return

        # Calculate PnL
        if original_action == 'BUY':
            pnl_cents = round((exit_price - tracked.fill_price) * 100, 1)
        else:
            pnl_cents = round((tracked.fill_price - exit_price) * 100, 1)

        tracked.status = 'CLOSED'
        tracked.exit_price = exit_price
        tracked.exit_ts = time.time()
        tracked.exit_pnl_cents = pnl_cents
        tracked.exit_strategy = strategy

        acct.total_exits += 1
        acct.total_pnl_cents += pnl_cents
        if pnl_cents > 0:
            acct.wins += 1
        elif pnl_cents < 0:
            acct.losses += 1

        engine = tracked.engine
        if engine not in acct.engine_pnl:
            acct.engine_pnl[engine] = []
        acct.engine_pnl[engine].append(pnl_cents)

        logger.warning(
            f"{LOG_PREFIX} [{account_id}] EXIT {'✅' if pnl_cents > 0 else '❌'}: "
            f"{symbol} {strategy} | fill=${tracked.fill_price:.2f} → exit=${exit_price:.2f} "
            f"PnL={pnl_cents:+.0f}c | engine={engine} | "
            f"day: {acct.total_exits}exits {acct.total_pnl_cents:+.0f}c "
            f"WR={acct.wins}/{acct.total_exits}"
        )

    # ═══════════════════════════════════════════════════════════
    # MAIN CHECK CYCLE (every 30s)
    # ═══════════════════════════════════════════════════════════

    def check_cycle(self, account_id: str = ''):
        """
        Main monitoring cycle — call every 30 seconds.

        Args:
            account_id: If specified, only check this account's orders.
                        In Dual Process mode, each account phase passes its own ID
                        so logs don't mix between HAMPRO and IBKR_PED.
                        If empty, checks all accounts (single-process RUNALL mode).
        
        Returns:
            'EOD' if end-of-day triggered (15:58 ET), None otherwise.
            Callers should stop the trading loop when 'EOD' is returned.
        """
        now = time.time()
        if now - self._last_check_ts < CHECK_INTERVAL_SEC - 2:
            return  # Too soon
        self._last_check_ts = now
        self._cycle_count += 1

        # ── EOD CHECK (15:58 ET = once per day) ──
        try:
            from zoneinfo import ZoneInfo
            from datetime import datetime
            et_now = datetime.now(ZoneInfo('America/New_York'))
            et_time = et_now.hour * 100 + et_now.minute  # e.g. 1558
            if et_time >= 1558 and not self._eod_triggered:
                self._eod_triggered = True
                logger.warning(f"{LOG_PREFIX} ══ EOD TRIGGERED @ {et_now.strftime('%H:%M ET')} ══")
                self.check_eod()
                return 'EOD'
        except Exception as e:
            logger.debug(f"{LOG_PREFIX} EOD time check error: {e}")

        # Update PFF
        pff_price = self._get_pff_price()
        pff_state = self._pff_monitor.update(pff_price)

        # Determine which accounts to check
        if account_id and account_id in self._accounts:
            accounts_to_check = {account_id: self._accounts[account_id]}
        elif account_id:
            # Account hasn't been seen yet (no fills/orders tracked)
            return
        else:
            accounts_to_check = self._accounts

        for acct_id, acct in accounts_to_check.items():
            open_orders = []
            filled_orders = []
            alerts = []

            for key, order in list(acct.tracked_orders.items()):
                if order.status in ('CLOSED', 'OV', 'CANCELLED'):
                    continue

                # Update market data
                tt_price, tt_venue = self._get_truth_tick(order.symbol)
                bid, ask = self._get_l1(order.symbol)

                order.current_bid = bid
                order.current_ask = ask
                order.current_spread = round(ask - bid, 4) if bid > 0 and ask > 0 else 0
                order.current_pff = pff_price
                order.current_truth_tick = tt_price
                order.pff_delta_from_create = round(pff_price - order.pff_at_create, 4) if order.pff_at_create > 0 else 0
                order.last_check_ts = now
                order.check_count += 1

                if tt_venue and tt_venue not in order.venue_hints:
                    order.venue_hints.append(tt_venue)
                    if len(order.venue_hints) > 10:
                        order.venue_hints = order.venue_hints[-10:]

                # ── OPEN ORDER ANALYSIS ──
                if order.status == 'OPEN':
                    self._analyze_open_order(order, tt_price, bid, ask, pff_price, pff_state, alerts)
                    open_orders.append(order)

                # ── FILLED ORDER ANALYSIS ──
                elif order.status == 'FILLED':
                    self._analyze_filled_order(order, tt_price, bid, ask, pff_price, pff_state, alerts)
                    filled_orders.append(order)

            # ── CYCLE LOG (every 30s per account) ──
            if open_orders or filled_orders:
                self._log_cycle_summary(acct_id, acct, open_orders, filled_orders, pff_price, pff_state, alerts)

            # ── SAVE SNAPSHOT TO REDIS (for QAgent) ──
            self._save_snapshot_to_redis(acct_id, acct, open_orders, filled_orders, pff_price, pff_state, alerts)

    def _analyze_open_order(
        self, order: TrackedOrder, tt_price: float,
        bid: float, ask: float, pff_price: float,
        pff_state: str, alerts: List[str],
    ):
        """Analyze an unfilled open order — why hasn't it filled?"""
        now = time.time()
        age_min = (now - order.created_ts) / 60 if order.created_ts > 0 else 0

        # Distance calculation
        if order.price > 0 and tt_price > 0:
            if order.action == 'BUY':
                order.price_distance_cents = round((tt_price - order.price) * 100, 1)
            else:
                order.price_distance_cents = round((order.price - tt_price) * 100, 1)

        # Fill probability
        dist = order.price_distance_cents
        if dist <= 2:
            order.fill_probability = 'LIKELY'
        elif dist <= 5:
            order.fill_probability = 'POSSIBLE'
        elif dist <= 10:
            order.fill_probability = 'WAITING'
        else:
            order.fill_probability = 'UNLIKELY'

        if age_min > STALE_ORDER_MINUTES and order.fill_probability not in ('LIKELY',):
            order.fill_probability = 'STALE'

        # Truth tick trend analysis
        tt_trend = self._get_truth_tick_trend(order.symbol)
        trend_dir = tt_trend.get('trend', 'UNKNOWN')
        dominant_venue = tt_trend.get('dominant_venue', '')

        # BUY order + FALLING ticks = might fill soon
        if order.action == 'BUY' and trend_dir == 'FALLING' and dist <= 5:
            note = f"TT FALLING ({tt_trend['velocity']:+.3f}/tick) — fill probability increasing"
            if note not in order.analysis_notes:
                order.analysis_notes.append(note)

        # BUY order + RISING ticks = moving away
        if order.action == 'BUY' and trend_dir == 'RISING' and dist > 5:
            note = f"TT RISING, moving AWAY from order — fill unlikely"
            if note not in order.analysis_notes:
                order.analysis_notes.append(note)

        # Venue hint
        if dominant_venue and dominant_venue not in order.venue_hints:
            order.venue_hints.append(dominant_venue)

        # PFF check for BUY orders (PFF dropping = bad for long fills)
        if order.action == 'BUY' and order.pff_delta_from_create < PFF_CAUTION_THRESHOLD:
            note = f"PFF dropped {order.pff_delta_from_create:+.3f} since order — fill risky"
            if note not in order.analysis_notes:
                order.analysis_notes.append(note)
            alerts.append(f"⚠️ {order.symbol} BUY@{order.price:.2f}: PFF↓{order.pff_delta_from_create:+.3f}")

        # PFF check for SELL orders (PFF rising = bad for short fills)
        if order.action in ('SELL', 'SHORT') and order.pff_delta_from_create > PFF_BULL_CAUTION_THRESHOLD:
            note = f"PFF rose {order.pff_delta_from_create:+.3f} since order — short fill risky"
            if note not in order.analysis_notes:
                order.analysis_notes.append(note)
            alerts.append(f"⚠️ {order.symbol} SELL@{order.price:.2f}: PFF↑{order.pff_delta_from_create:+.3f}")

        # Can we frontrun a truth tick?
        if order.action == 'BUY' and tt_price > 0 and order.price > 0:
            if tt_price <= order.price + 0.02:
                note = f"Truth tick ${tt_price:.2f} near order ${order.price:.2f} — fill likely soon"
                if note not in order.analysis_notes:
                    order.analysis_notes.append(note)

        # Stale alert
        if age_min > STALE_ORDER_MINUTES and order.fill_probability in ('UNLIKELY', 'STALE'):
            alerts.append(
                f"🕐 {order.symbol} {order.action}@{order.price:.2f} "
                f"STALE {age_min:.0f}min dist={dist:+.0f}c "
                f"tt_trend={trend_dir} venue={dominant_venue}"
            )

    def _analyze_filled_order(
        self, order: TrackedOrder, tt_price: float,
        bid: float, ask: float, pff_price: float,
        pff_state: str, alerts: List[str],
    ):
        """Analyze a filled order — unrealized PnL, exit feasibility, truth tick trend."""
        if order.fill_price <= 0:
            return

        order.pff_delta_from_fill = round(
            pff_price - order.pff_at_fill, 4
        ) if order.pff_at_fill > 0 else 0

        # ── PER-ORDER PFF TRACKING (cents) ──
        if order.pff_at_fill > 0 and pff_price > 0:
            order.pff_fill_to_now_c = round((pff_price - order.pff_at_fill) * 100, 1)
        if order.pff_at_create > 0 and pff_price > 0:
            order.pff_sent_to_now_c = round((pff_price - order.pff_at_create) * 100, 1)

        # ── PER-ORDER PFF STATE ──
        # For BUY: PFF dropping is bad → CAUTION/BEARISH
        # For SELL/SHORT: PFF rising is bad → BULL_CAUTION/BULLISH
        # Uses fill→now delta as the primary signal (post-fill movement matters most)
        pff_delta_c = order.pff_fill_to_now_c
        if order.action == 'BUY':
            # PFF dropping = bad for long
            if pff_delta_c <= PFF_BEARISH_THRESHOLD * 100:
                order.pff_order_state = 'BEARISH'
            elif pff_delta_c <= PFF_CAUTION_THRESHOLD * 100:
                order.pff_order_state = 'CAUTION'
            else:
                order.pff_order_state = 'NORMAL'
        elif order.action in ('SELL', 'SHORT'):
            # PFF rising = bad for short
            if pff_delta_c >= PFF_BULLISH_THRESHOLD * 100:
                order.pff_order_state = 'BULLISH'
            elif pff_delta_c >= PFF_BULL_CAUTION_THRESHOLD * 100:
                order.pff_order_state = 'BULL_CAUTION'
            else:
                order.pff_order_state = 'NORMAL'

        # Truth tick trend (post-fill)
        tt_trend = self._get_truth_tick_trend(order.symbol)
        trend_dir = tt_trend.get('trend', 'UNKNOWN')
        trend_vel = tt_trend.get('velocity', 0)

        # Unrealized PnL
        if tt_price > 0:
            if order.action == 'BUY':
                pnl_c = round((tt_price - order.fill_price) * 100, 1)
            else:
                pnl_c = round((order.fill_price - tt_price) * 100, 1)

            order.price_distance_cents = pnl_c  # reuse as unrealized PnL

            # Track max favorable/adverse
            if pnl_c > order.max_favorable_cents:
                order.max_favorable_cents = pnl_c
            if pnl_c < order.max_adverse_cents:
                order.max_adverse_cents = pnl_c

            # Exit feasibility — L1
            min_exit_price = order.fill_price + MIN_PROFIT_CENTS / 100
            l1_tp_ok = False
            l2_tp_ok = False
            l2_tp_price = 0.0

            if order.action == 'BUY':
                possible_exit = ask - 0.01 if ask > 0 else 0
                if possible_exit >= min_exit_price:
                    l1_tp_ok = True
                    note = f"L1_TP: SELL@${possible_exit:.2f} → +{round((possible_exit - order.fill_price)*100)}c"
                    if note not in order.analysis_notes:
                        order.analysis_notes.append(note)
                else:
                    # L2 check — find a deeper ask level
                    l2_asks = self._get_l2_asks(order.symbol)
                    for l2_price, l2_size in l2_asks:
                        l2_exit = l2_price - 0.01
                        if l2_exit >= min_exit_price and l2_size >= 100:
                            l2_tp_ok = True
                            l2_tp_price = l2_exit
                            note = (f"L2_TP: SELL@${l2_exit:.2f} (behind ask ${l2_price:.2f}/{l2_size}lot) "
                                    f"→ +{round((l2_exit - order.fill_price)*100)}c")
                            if note not in order.analysis_notes:
                                order.analysis_notes.append(note)
                            break
            else:
                possible_exit = bid + 0.01 if bid > 0 else 0
                max_cover_price = order.fill_price - MIN_PROFIT_CENTS / 100
                if 0 < possible_exit <= max_cover_price:
                    l1_tp_ok = True
                    note = f"L1_TP: BUY@${possible_exit:.2f} → +{round((order.fill_price - possible_exit)*100)}c"
                    if note not in order.analysis_notes:
                        order.analysis_notes.append(note)

            # BUY fill + truth ticks FALLING = bad for us
            if order.action == 'BUY' and trend_dir == 'FALLING' and pnl_c < 0:
                note = f"⚠ TT FALLING post-fill ({trend_vel:+.3f}/tick), unrealized={pnl_c:+.0f}c"
                if note not in order.analysis_notes:
                    order.analysis_notes.append(note)

            # SELL fill + truth ticks RISING = bad for short
            if order.action in ('SELL', 'SHORT') and trend_dir == 'RISING' and pnl_c < 0:
                note = f"⚠ TT RISING post-fill ({trend_vel:+.3f}/tick), unrealized={pnl_c:+.0f}c — bad for short"
                if note not in order.analysis_notes:
                    order.analysis_notes.append(note)

            # BEARISH PFF alert (bad for longs) — uses per-order state
            if order.pff_order_state == 'BEARISH':
                alerts.append(
                    f"🔴 {order.symbol} BEARISH: fill@${order.fill_price:.2f} "
                    f"PFF sent→fill={order.pff_sent_to_fill_c:+.1f}c "
                    f"fill→now={order.pff_fill_to_now_c:+.1f}c — aggressive exit needed"
                )
            elif order.pff_order_state == 'CAUTION':
                alerts.append(
                    f"⚠️ {order.symbol} CAUTION: fill@${order.fill_price:.2f} "
                    f"PFF sent→fill={order.pff_sent_to_fill_c:+.1f}c "
                    f"fill→now={order.pff_fill_to_now_c:+.1f}c"
                )

            # BULLISH PFF alert (bad for shorts) — uses per-order state
            if order.pff_order_state == 'BULLISH':
                alerts.append(
                    f"🟢 {order.symbol} BULLISH: fill@${order.fill_price:.2f} "
                    f"PFF sent→fill={order.pff_sent_to_fill_c:+.1f}c "
                    f"fill→now={order.pff_fill_to_now_c:+.1f}c — aggressive cover needed"
                )
            elif order.pff_order_state == 'BULL_CAUTION':
                alerts.append(
                    f"⚠️ {order.symbol} BULL_CAUTION: fill@${order.fill_price:.2f} "
                    f"PFF sent→fill={order.pff_sent_to_fill_c:+.1f}c "
                    f"fill→now={order.pff_fill_to_now_c:+.1f}c"
                )

            # Loss alert
            if pnl_c < -10:
                alerts.append(
                    f"❌ {order.symbol} {order.action}@${order.fill_price:.2f} "
                    f"unrealized={pnl_c:+.0f}c tt=${tt_price:.2f} "
                    f"trend={trend_dir} L1_TP={'✅' if l1_tp_ok else '❌'} L2_TP={'✅' if l2_tp_ok else '❌'}"
                )

    def _log_cycle_summary(
        self, account_id: str, acct: AccountState,
        open_orders: List[TrackedOrder], filled_orders: List[TrackedOrder],
        pff_price: float, pff_state: str, alerts: List[str],
    ):
        """Log cycle summary for this account."""
        stale = sum(1 for o in open_orders if o.fill_probability in ('STALE', 'UNLIKELY'))
        likely = sum(1 for o in open_orders if o.fill_probability == 'LIKELY')
        in_profit = sum(1 for o in filled_orders if o.price_distance_cents > 2)
        in_loss = sum(1 for o in filled_orders if o.price_distance_cents < -2)

        wr_pct = round(acct.wins / acct.total_exits * 100) if acct.total_exits > 0 else 0

        # Cost basis summary
        cb_summary = ''
        if acct.symbol_costs:
            active = [(s, cb) for s, cb in acct.symbol_costs.items() if cb.net_qty != 0]
            if active:
                cb_parts = [f"{s}:{cb.net_qty}@{cb.avg_buy_cost:.2f}" for s, cb in active[:5]]
                cb_summary = f" | CB: {', '.join(cb_parts)}"

        bull_st = self._pff_monitor.bull_state
        pff_label = f"{pff_state}" if bull_st == 'NORMAL' else f"↓{pff_state}/↑{bull_st}"

        logger.info(
            f"{LOG_PREFIX} [{account_id}] ══ CYCLE #{self._cycle_count}: "
            f"OPEN={len(open_orders)}({likely}likely/{stale}stale) "
            f"FILLED={len(filled_orders)}({in_profit}profit/{in_loss}loss) | "
            f"PFF=${pff_price:.2f}[{pff_label}] | "
            f"day: {acct.total_fills}fills {acct.total_exits}exits "
            f"{acct.total_pnl_cents:+.0f}c WR={wr_pct}%{cb_summary}"
        )

        # Log alerts
        for alert in alerts[:5]:
            logger.warning(f"{LOG_PREFIX} [{account_id}] {alert}")

        # Detailed open order report (every 5 cycles = ~2.5 min)
        if self._cycle_count % 5 == 1 and open_orders:
            for o in open_orders[:10]:
                age_min = (time.time() - o.created_ts) / 60 if o.created_ts > 0 else 0
                tt_trend = self._get_truth_tick_trend(o.symbol)
                pff_sent_now = round((pff_price - o.pff_at_create) * 100, 1) if o.pff_at_create > 0 else 0
                logger.info(
                    f"{LOG_PREFIX} [{account_id}] OPEN {o.action} {o.symbol} "
                    f"@${o.price:.2f} {o.lot}lot [{o.engine}] | "
                    f"age={age_min:.0f}min dist={o.price_distance_cents:+.0f}c "
                    f"prob={o.fill_probability} | "
                    f"bid=${o.current_bid:.2f} ask=${o.current_ask:.2f} "
                    f"tt=${o.current_truth_tick:.2f} "
                    f"trend={tt_trend['trend']}({tt_trend['velocity']:+.3f}) "
                    f"venue={tt_trend['dominant_venue']}({tt_trend['tick_count']}ticks) | "
                    f"PFF sent→now={pff_sent_now:+.1f}c"
                )

        # Detailed filled order report (every 5 cycles = ~2.5 min)
        if self._cycle_count % 5 == 1 and filled_orders:
            for o in filled_orders[:10]:
                hold_min = (time.time() - o.fill_ts) / 60 if o.fill_ts > 0 else 0
                tt_trend = self._get_truth_tick_trend(o.symbol)
                # Per-order PFF state emoji
                pff_st_icon = '🟢' if o.pff_order_state == 'NORMAL' else (
                    '🟡' if o.pff_order_state in ('CAUTION', 'BULL_CAUTION') else '🔴'
                )
                logger.info(
                    f"{LOG_PREFIX} [{account_id}] HELD {o.action} {o.symbol} "
                    f"fill@${o.fill_price:.2f} {o.lot}lot [{o.engine}] | "
                    f"hold={hold_min:.0f}min pnl={o.price_distance_cents:+.0f}c "
                    f"(max+{o.max_favorable_cents:.0f}c/max{o.max_adverse_cents:+.0f}c) | "
                    f"tt_trend={tt_trend['trend']}({tt_trend['velocity']:+.3f}) | "
                    f"PFF{pff_st_icon}[{o.pff_order_state}] "
                    f"sent→fill={o.pff_sent_to_fill_c:+.1f}c "
                    f"fill→now={o.pff_fill_to_now_c:+.1f}c "
                    f"sent→now={o.pff_sent_to_now_c:+.1f}c"
                )

    def _save_snapshot_to_redis(
        self, account_id: str, acct: AccountState,
        open_orders: List[TrackedOrder], filled_orders: List[TrackedOrder],
        pff_price: float, pff_state: str, alerts: List[str],
    ):
        """Save structured snapshot to Redis for QAgent consumption."""
        try:
            r = self._get_redis()

            snapshot = {
                "ts": datetime.now().isoformat(),
                "account_id": account_id,
                "cycle": self._cycle_count,
                "pff": {
                    "price": pff_price,
                    "bear_state": pff_state,
                    "bull_state": self._pff_monitor.bull_state,
                    "state": pff_state,  # legacy compat
                },
                "open_orders": {
                    "count": len(open_orders),
                    "likely": sum(1 for o in open_orders if o.fill_probability == 'LIKELY'),
                    "stale": sum(1 for o in open_orders if o.fill_probability in ('STALE', 'UNLIKELY')),
                    "details": [
                        {
                            "s": o.symbol, "act": o.action, "p": o.price,
                            "eng": o.engine, "dist_c": o.price_distance_cents,
                            "prob": o.fill_probability,
                            "age_min": round((time.time() - o.created_ts) / 60, 1) if o.created_ts > 0 else 0,
                        }
                        for o in open_orders[:20]
                    ],
                },
                "filled_positions": {
                    "count": len(filled_orders),
                    "in_profit": sum(1 for o in filled_orders if o.price_distance_cents > 2),
                    "in_loss": sum(1 for o in filled_orders if o.price_distance_cents < -2),
                    "details": [
                        {
                            "s": o.symbol, "act": o.action, "fill": o.fill_price,
                            "eng": o.engine, "pnl_c": o.price_distance_cents,
                            "pff_at_sent": round(o.pff_at_create, 2),
                            "pff_at_fill": round(o.pff_at_fill, 2),
                            "pff_now": round(o.current_pff, 2),
                            "pff_sent_fill_c": o.pff_sent_to_fill_c,
                            "pff_fill_now_c": o.pff_fill_to_now_c,
                            "pff_sent_now_c": o.pff_sent_to_now_c,
                            "pff_state": o.pff_order_state,
                            "max_fav": o.max_favorable_cents,
                            "max_adv": o.max_adverse_cents,
                        }
                        for o in filled_orders[:20]
                    ],
                },
                "daily_stats": {
                    "orders_sent": acct.total_orders_sent,
                    "fills": acct.total_fills,
                    "exits": acct.total_exits,
                    "pnl_cents": round(acct.total_pnl_cents, 1),
                    "wins": acct.wins,
                    "losses": acct.losses,
                    "wr_pct": round(acct.wins / acct.total_exits * 100, 1) if acct.total_exits > 0 else 0,
                    "engine_fills": dict(acct.engine_fills),
                    "engine_orders": dict(acct.engine_orders),
                },
                "cost_basis": {
                    sym: cb.to_compact()
                    for sym, cb in acct.symbol_costs.items()
                    if cb.buy_qty > 0 or cb.sell_qty > 0
                },
                "alerts": alerts[:10],
            }

            r.set(
                f"psfalgo:tracker:snapshot:{account_id}",
                json.dumps(snapshot, ensure_ascii=False, default=str),
                ex=120,  # 2 minute TTL
            )

        except Exception as e:
            logger.debug(f"{LOG_PREFIX} Redis snapshot save error: {e}")

    # ═══════════════════════════════════════════════════════════
    # PUBLIC API
    # ═══════════════════════════════════════════════════════════

    def get_snapshot(self, account_id: str) -> Dict[str, Any]:
        """Get structured snapshot for QAgent or dashboard."""
        acct = self._accounts.get(account_id)
        if not acct:
            return {"account_id": account_id, "status": "no_data"}

        open_orders = [o for o in acct.tracked_orders.values() if o.status == 'OPEN']
        filled_orders = [o for o in acct.tracked_orders.values() if o.status == 'FILLED']

        return {
            "account_id": account_id,
            "open_count": len(open_orders),
            "filled_count": len(filled_orders),
            "daily_fills": acct.total_fills,
            "daily_exits": acct.total_exits,
            "daily_pnl_cents": acct.total_pnl_cents,
            "wins": acct.wins,
            "losses": acct.losses,
            "pff_state": self._pff_monitor.state,
            "pff_price": self._pff_monitor.last_price,
            "engine_stats": {
                eng: {
                    "orders": acct.engine_orders.get(eng, 0),
                    "fills": acct.engine_fills.get(eng, 0),
                    "pnl": acct.engine_pnl.get(eng, []),
                }
                for eng in set(list(acct.engine_orders.keys()) + list(acct.engine_fills.keys()))
            },
            "cost_basis": {
                sym: cb.to_compact()
                for sym, cb in acct.symbol_costs.items()
                if cb.buy_qty > 0 or cb.sell_qty > 0
            },
        }

    def reset_daily(self):
        """Reset daily counters (call at market open)."""
        for acct in self._accounts.values():
            acct.total_orders_sent = 0
            acct.total_fills = 0
            acct.total_exits = 0
            acct.total_pnl_cents = 0.0
            acct.wins = 0
            acct.losses = 0
            acct.cancelled = 0
            acct.engine_orders.clear()
            acct.engine_fills.clear()
            acct.engine_pnl.clear()
            acct.symbol_costs.clear()
            # Keep only OPEN and FILLED orders, remove CLOSED/OV/CANCELLED
            acct.tracked_orders = {
                k: v for k, v in acct.tracked_orders.items()
                if v.status in ('OPEN', 'FILLED')
            }

        self._pff_monitor.reset_anchor()
        self._cycle_count = 0
        self._eod_triggered = False
        logger.info(f"{LOG_PREFIX} Daily reset complete")

    def check_eod(self):
        """
        End-of-Day handler — call around 15:50 ET.
        
        For each FILLED order (not yet exited):
        1. Log final market snapshot
        2. Mark as OV (overnight)
        3. Log EOD summary per account
        """
        for account_id, acct in self._accounts.items():
            ov_count = 0
            filled = [o for o in acct.tracked_orders.values() if o.status == 'FILLED']

            for order in filled:
                tt_price, tt_venue = self._get_truth_tick(order.symbol)
                bid, ask = self._get_l1(order.symbol)
                tt_trend = self._get_truth_tick_trend(order.symbol)

                # Final PnL
                if order.action == 'BUY' and tt_price > 0:
                    final_pnl_c = round((tt_price - order.fill_price) * 100, 1)
                elif order.action in ('SELL', 'SHORT') and tt_price > 0:
                    final_pnl_c = round((order.fill_price - tt_price) * 100, 1)
                else:
                    final_pnl_c = 0

                order.status = 'OV'
                ov_count += 1

                logger.warning(
                    f"{LOG_PREFIX} [{account_id}] EOD→OV: {order.action} {order.symbol} "
                    f"fill@${order.fill_price:.2f} {order.lot}lot [{order.engine}] | "
                    f"final_pnl={final_pnl_c:+.0f}c "
                    f"(max+{order.max_favorable_cents:.0f}c/max{order.max_adverse_cents:+.0f}c) | "
                    f"tt=${tt_price:.2f} trend={tt_trend['trend']} "
                    f"bid=${bid:.2f} ask=${ask:.2f} | "
                    f"PFF_delta={order.pff_delta_from_fill:+.3f}"
                )

            if ov_count > 0:
                total_rpnl = sum(
                    cb.realized_pnl for cb in acct.symbol_costs.values()
                )
                logger.warning(
                    f"{LOG_PREFIX} [{account_id}] ══ EOD SUMMARY: "
                    f"{ov_count} positions → OV | "
                    f"day: {acct.total_fills}fills {acct.total_exits}exits "
                    f"{acct.total_pnl_cents:+.0f}c realized | "
                    f"symbol_rpnl=${total_rpnl:+.2f}"
                )


# ═══════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════

_tracker_instance: Optional[OrderLifecycleTracker] = None


def get_order_lifecycle_tracker() -> OrderLifecycleTracker:
    """Get or create the singleton tracker instance."""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = OrderLifecycleTracker()
    return _tracker_instance
