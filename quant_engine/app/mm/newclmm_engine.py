"""
NEWCLMM Engine — Truth Tick Dynamic Market Making Engine
========================================================

POS TAG:    MM
ENGINE TAG: NEWC
ORDER TAGS: MM_NEWC_LONG_INC, MM_NEWC_SHORT_INC,
            MM_NEWC_LONG_DEC, MM_NEWC_SHORT_DEC

STRATEGY (DYNAMIC — adapts to actual spread at trade time):
  Wide spread (≥25c):  Spread Capture — 12c profit, 5c tick, consec=1, 99% WR
  Med spread (10-25c): Mean Reversion — 25c profit, 10c tick, consec=3
  Narrow spread (<10c):Mean Reversion — 15c profit, 7c tick, consec=3

  Stop: NONE — preferred stocks are bond-like, mean-reversion holds

TRUTH TICK FRONTLAMA:
  - FNRA venue: sadece 100/200 lot geçerli
  - Non-FNRA (ARCA, NYSE, BATS, EDGX, etc.): ≥15 lot geçerli
  - Gerçek tick: ≥MIN_TICK_SIZE hareket (dynamic per spread)
  - Downtick = BUY sinyali, Uptick = SHORT sinyali
  - 3+ ardışık gerçek tick = STRONG sinyal → büyük lot

VALIDATED EDGE (1.46M simulation + TEST set):
  - BUY:   +5.46c avg, %89 WR, %79 capture, n=79,603
  - SHORT: +5.14c avg, %88 WR, %80 capture, n=78,756
  - 3-consec SHORT: +6.75c, %99 WR, %97 capture, n=115
  - Wide spread 12c: %99 WR (spread capture — proven)
  - Med spread 25c + 3-consec: %82 WR, $3K/day (sim)
"""

import json
import time
from datetime import datetime
from typing import List, Dict, Any, Optional
from collections import deque
from dataclasses import dataclass, field

from app.core.logger import logger
from app.core.redis_client import get_redis_client
from app.psfalgo.decision_models import DecisionRequest, Decision
from app.psfalgo.free_exposure_engine import get_free_exposure_engine


# ============================================================================
# DYNAMIC CONFIGURATION — adapts to actual spread at trade time
# ============================================================================
# Derived from 1.46M simulation (384 configs × 95 stocks × 40 days)
# Key insight: profit target MUST scale with spread and tick size.
# Flat 7c is suboptimal; wide spreads want 12c (spread capture),
# medium spreads want 25c (mean reversion), narrow wants 15c.

# Absolute minimums / fallbacks
MIN_TICK_SIZE_FLOOR = 0.05     # $0.05 (5c) — absolute minimum real tick
MIN_PROFIT_TARGET_FLOOR = 0.07 # $0.07 (7c) — never go below this
MIN_SPREAD_FLOOR = 0.05        # $0.05 (5c) — minimum spread to consider


def get_dynamic_config(spread_dollars: float) -> Dict[str, Any]:
    """
    Return optimal trading parameters based on actual spread.

    These values are derived from simulation results:
    - Wide spread (≥$0.25): Spread capture strategy
      99% WR, 12c profit sits INSIDE spread → near-guaranteed fill
    - Medium spread ($0.10-$0.25): Mean reversion
      82% WR, 25c profit, needs 3 consecutive ticks for confirmation
    - Narrow spread (<$0.10): Careful mean reversion
      80% WR, 15c profit, needs 3 consecutive, bigger tick filter

    Returns dict with:
      min_tick:       minimum price move to count as real tick ($)
      profit_target:  exit target distance from entry ($)
      entry_offset:   entry price offset as fraction of spread (0.0-1.0)
      min_consec:     minimum consecutive ticks to trigger entry
      strategy_name:  human-readable strategy label
    """
    spread_cents = spread_dollars * 100

    if spread_cents >= 25:
        # ═══ WIDE SPREAD: SPREAD CAPTURE ═══
        # Profit sits inside the spread → near-guaranteed fill
        # Simulation: 99% WR, EOD loss <1%, avg adverse 0c
        return {
            'min_tick': 0.05,       # 5c — small tick OK, spread catches it
            'profit_target': 0.12,  # 12c — well inside 25c+ spread
            'entry_offset': 0.10,   # 10% into spread (bid + 2-3c)
            'min_consec': 1,        # Every tick is a signal (high WR)
            'strategy_name': 'SPREAD_CAPTURE',
        }
    elif spread_cents >= 10:
        # ═══ MEDIUM SPREAD: MEAN REVERSION ═══
        # Need confirmation (3 consecutive) before entering
        # Simulation: 82% WR, $3K/day, EOD loss ~17%
        return {
            'min_tick': 0.10,       # 10c — filter noise in medium spread
            'profit_target': 0.25,  # 25c — full mean reversion distance
            'entry_offset': 0.10,   # 10% into spread
            'min_consec': 3,        # 3 consecutive ticks needed
            'strategy_name': 'MEAN_REVERSION',
        }
    else:
        # ═══ NARROW SPREAD: CAREFUL MEAN REVERSION ═══
        # Spread too tight for capture, need momentum confirmation
        # Simulation: 80% WR, needs strong signal
        return {
            'min_tick': 0.07,       # 7c — moderate filter
            'profit_target': 0.15,  # 15c — shorter mean reversion
            'entry_offset': 0.15,   # 15% into spread
            'min_consec': 3,        # 3 consecutive ticks needed
            'strategy_name': 'CAREFUL_MR',
        }


# Order type — ALL NEWCLMM orders are HIDDEN LIMIT
ORDER_TYPE = "LIMIT"        # Limit order
HIDDEN = True               # Always hidden — never show on book

# FNRA venue filter
FNRA_VENUE = 'FNRA'
FNRA_VALID_SIZES = frozenset({100, 200})  # Only 100/200 from FNRA
NON_FNRA_MIN_SIZE = 15                     # Others: ≥15 lot

# Consecutive tick (momentum signal)
CONSEC_STRONG = 3           # 3+ consecutive = STRONG signal (lot boost)
CONSEC_LOT_MULT = 1.5       # STRONG signals get 1.5x lot

# Lot sizing
MIN_LOT = 200               # Minimum lot size (always >=200)

# Risk / throttle
COOLDOWN_SECONDS = 60       # Same symbol, same direction cooldown
MAX_ACTIVE_NEWC = 70        # Max active NEWC entries per cycle

# Priority system — training-validated symbols get first scan
MIN_PRIORITY_SIGNALS = 15   # If >=15 signals from priority list, skip others
PRIORITY_SCORE_BONUS = 25.0 # Priority symbols get +25 score in ranking

# 95 symbols from truth tick training data (validated edge)
PRIORITY_SYMBOLS = frozenset({
    'ACP PRA', 'ACR PRC', 'ACR PRD', 'ADC PRA', 'AHH PRA',
    'AHL PRD', 'AHL PRF', 'AMH PRG', 'AMH PRH', 'BAC PRB',
    'BAC PRE', 'BIPJ', 'BML PRG', 'BML PRJ', 'BOH PRB',
    'CFG PRE', 'CHMI PRA', 'CHMI PRB', 'CHSCO', 'CMRE PRB',
    'CMRE PRD', 'CRBD', 'DCOMG', 'DCOMP', 'DDT',
    'DSX PRB', 'DTB', 'ETI PR', 'FCNCO', 'FGSN',
    'FHN PRF', 'FITBI', 'FITBO', 'FITBP', 'FULTP',
    'GGT PRG', 'GMRE PRA', 'GNL PRB', 'GOODO', 'GPJA',
    'GS PRC', 'GSL PRB', 'HIG PRG', 'HTFC', 'HWCPZ',
    'INN PRE', 'JPM PRD', 'KEY PRJ', 'LANDO', 'LFT PRA',
    'LNC PRD', 'LOB PRA', 'MBINN', 'MET PRA', 'MFA PRB',
    'MGR', 'MGRE', 'MITT PRA', 'MITT PRB', 'MS PRI',
    'MS PRL', 'MTB PRH', 'NCV PRA', 'NHPBP', 'OCCIN',
    'OCCIO', 'OXLCI', 'OXLCP', 'OXSQH', 'PEB PRF',
    'PMTU', 'PRIF PRD', 'PSEC PRA', 'REXR PRB', 'RF PRC',
    'RITM PRA', 'RITM PRD', 'RLJ PRA', 'SAY', 'SB PRD',
    'SCHW PRD', 'SEAL PRA', 'SHO PRH', 'SSSSL', 'SYF PRA',
    'TDS PRV', 'TRTN PRB', 'UMBFO', 'VLYPO', 'VNO PRL',
    'VNO PRO', 'VOYA PRB', 'WAL PRA', 'WBS PRF', 'WBS PRG',
})

# Engine toggle — DEFAULT OFF (user enables from UI before dual process)
DEFAULT_ENABLED = False
REDIS_ENABLED_KEY = 'newclmm:enabled'  # Redis key for persistent toggle


# ============================================================================
# PER-SYMBOL STATE
# ============================================================================

@dataclass
class SymbolTickState:
    """Track consecutive real tick direction per symbol"""
    # Tick counters
    last_valid_price: float = 0.0
    consec_down: int = 0         # Consecutive ≥5c downtick count
    consec_up: int = 0           # Consecutive ≥5c uptick count
    last_direction: str = ''     # 'DOWN' or 'UP'
    last_tick_ts: float = 0.0    # Timestamp of last processed tick
    last_tick_delta: float = 0.0 # Last real tick price change (for scoring)
    
    # Active position tracking (NEWC-internal)
    long_entry_price: float = 0.0    # 0 = no active long
    short_entry_price: float = 0.0   # 0 = no active short
    long_entry_ts: float = 0.0
    short_entry_ts: float = 0.0
    
    # FILL PRICE tracking (actual fill from broker, or simulated in paper)
    fill_price_long: float = 0.0     # Real fill price for active long
    fill_price_short: float = 0.0    # Real fill price for active short
    profit_order_sent_long: bool = False   # Profit-take order already sent?
    profit_order_sent_short: bool = False
    
    # Dynamic profit target used for THIS entry (set at entry time)
    profit_target_long: float = 0.07   # Actual $ profit target for active long
    profit_target_short: float = 0.07  # Actual $ profit target for active short
    strategy_long: str = ''            # Strategy name used (SPREAD_CAPTURE etc)
    strategy_short: str = ''           # Strategy name used
    
    # Cooldown
    last_buy_signal_ts: float = 0.0
    last_short_signal_ts: float = 0.0
    
    # Performance counters (intraday)
    trades_today: int = 0
    pnl_today_cents: float = 0.0
    wins_today: int = 0


# ============================================================================
# ENGINE
# ============================================================================

class NewCLMMEngine:
    """
    NEWCLMM — Truth Tick Spread Capture Market Making Engine.
    
    Completely independent from GREATEST_MM.
    Uses Dual Tag v4 system: pos_tag=MM, engine_tag=NEWC.
    """
    
    ENGINE_NAME = "NEWC"
    POS_TAG = "MM"
    ENGINE_TAG = "NEWC"
    PRIORITY = 8  # Slightly higher than GREATEST_MM (10)
    
    def __init__(self):
        self._redis = None
        # State keyed by "{account_id}:{symbol}" for dual-process isolation
        self._states: Dict[str, SymbolTickState] = {}
        self._enabled: bool = DEFAULT_ENABLED  # OFF by default
        logger.info(
            f"[{self.ENGINE_NAME}] Engine initialized | "
            f"ENABLED={self._enabled} "
            f"DYNAMIC CONFIG (spread-based profit targets) "
            f"FLOOR: tick=${MIN_TICK_SIZE_FLOOR:.2f} profit=${MIN_PROFIT_TARGET_FLOOR:.2f}"
        )
    
    # =====================================================================
    # ENABLE / DISABLE TOGGLE
    # =====================================================================
    
    @property
    def enabled(self) -> bool:
        """Check if engine is enabled (memory + Redis fallback)"""
        return self._enabled
    
    def set_enabled(self, value: bool):
        """Toggle engine on/off. Also persists to Redis."""
        old = self._enabled
        self._enabled = value
        # Persist to Redis
        redis = self._get_redis()
        if redis:
            try:
                redis.set(REDIS_ENABLED_KEY, '1' if value else '0')
            except Exception:
                pass
        logger.warning(
            f"[{self.ENGINE_NAME}] {'✅ ENABLED' if value else '❌ DISABLED'}"
            f"{' (was ' + ('ON' if old else 'OFF') + ')' if old != value else ''}"
        )
    
    def sync_enabled_from_redis(self):
        """Sync enabled state from Redis (call on startup / cycle start)"""
        redis = self._get_redis()
        if redis:
            try:
                val = redis.get(REDIS_ENABLED_KEY)
                if val is not None:
                    if isinstance(val, bytes):
                        val = val.decode('utf-8')
                    self._enabled = val == '1'
            except Exception:
                pass
    
    # =====================================================================
    # FILL EVENT HANDLING
    # =====================================================================
    
    def on_fill(self, symbol: str, action: str, fill_price: float, tag: str = '', account_id: str = ''):
        """
        Called when a NEWC-tagged fill event arrives from broker.
        
        Records the actual fill price so profit-take can use it.
        Logs rich metrics: PFF@fill, daily PnL, win rate, strategy.
        
        Args:
            symbol: e.g. 'ACGLO'
            action: 'BUY' or 'SELL' (the action that was FILLED)
            fill_price: actual execution price
            tag: order tag (e.g. 'MM_NEWC_LONG_INC')
            account_id: HAMPRO or IBKR_PED (for dual-process isolation)
        """
        if not account_id:
            try:
                from app.trading.trading_account_context import get_trading_context
                ctx = get_trading_context()
                account_id = ctx.trading_mode.value if ctx else 'DEFAULT'
            except Exception:
                account_id = 'DEFAULT'
        state = self._get_state(symbol, account_id)
        action = action.upper()
        is_priority = symbol in PRIORITY_SYMBOLS
        pri_flag = '[PRI]' if is_priority else '[OTH]'
        
        if action == 'BUY':
            if 'DEC' in tag or state.fill_price_short > 0:
                # Closing a SHORT — profit-take completed (cover)
                entry = state.fill_price_short
                pnl_cents = (entry - fill_price) * 100 if entry > 0 else 0
                state.trades_today += 1
                if pnl_cents > 0:
                    state.wins_today += 1
                state.pnl_today_cents += pnl_cents
                wr = (state.wins_today / state.trades_today * 100) if state.trades_today > 0 else 0
                logger.warning(
                    f"[{self.ENGINE_NAME}] FILL TP SHORT {pri_flag} {symbol} "
                    f"BUY(cover)@${fill_price:.2f} | PFF@${entry:.2f} -> ${fill_price:.2f} "
                    f"PnL={pnl_cents:+.0f}c | strat={state.strategy_short} "
                    f"| day: {state.trades_today}trades {state.pnl_today_cents:+.0f}c "
                    f"WR={wr:.0f}% ({state.wins_today}W) | tag={tag}"
                )
                state.fill_price_short = 0.0
                state.short_entry_price = 0.0
                state.profit_order_sent_short = False
                state.profit_target_short = MIN_PROFIT_TARGET_FLOOR
                state.strategy_short = ''
            else:
                # Opening a LONG position
                state.fill_price_long = fill_price
                state.profit_order_sent_long = False
                pt = state.profit_target_long
                strat = state.strategy_long or 'DYNAMIC'
                logger.warning(
                    f"[{self.ENGINE_NAME}] FILL ENTRY {pri_flag} {symbol} "
                    f"BUY@${fill_price:.2f} HIDDEN | TP target=${fill_price + pt:.2f} "
                    f"(+{pt*100:.0f}c) | strat={strat} "
                    f"| day: {state.trades_today}trades {state.pnl_today_cents:+.0f}c | tag={tag}"
                )
        elif action == 'SELL':
            if 'DEC' in tag or state.fill_price_long > 0:
                # Closing a LONG — profit-take completed
                entry = state.fill_price_long
                pnl_cents = (fill_price - entry) * 100 if entry > 0 else 0
                state.trades_today += 1
                if pnl_cents > 0:
                    state.wins_today += 1
                state.pnl_today_cents += pnl_cents
                wr = (state.wins_today / state.trades_today * 100) if state.trades_today > 0 else 0
                logger.warning(
                    f"[{self.ENGINE_NAME}] FILL TP LONG {pri_flag} {symbol} "
                    f"SELL@${fill_price:.2f} | PFF@${entry:.2f} -> ${fill_price:.2f} "
                    f"PnL={pnl_cents:+.0f}c | strat={state.strategy_long} "
                    f"| day: {state.trades_today}trades {state.pnl_today_cents:+.0f}c "
                    f"WR={wr:.0f}% ({state.wins_today}W) | tag={tag}"
                )
                state.fill_price_long = 0.0
                state.long_entry_price = 0.0
                state.profit_order_sent_long = False
                state.profit_target_long = MIN_PROFIT_TARGET_FLOOR
                state.strategy_long = ''
            else:
                # Opening a SHORT position
                state.fill_price_short = fill_price
                state.profit_order_sent_short = False
                pt = state.profit_target_short
                strat = state.strategy_short or 'DYNAMIC'
                logger.warning(
                    f"[{self.ENGINE_NAME}] FILL ENTRY {pri_flag} {symbol} "
                    f"SELL(short)@${fill_price:.2f} HIDDEN | TP target=${fill_price - pt:.2f} "
                    f"(-{pt*100:.0f}c) | strat={strat} "
                    f"| day: {state.trades_today}trades {state.pnl_today_cents:+.0f}c | tag={tag}"
                )
    
    # =====================================================================
    # REDIS ACCESS
    # =====================================================================
    
    def _get_redis(self):
        if self._redis is None:
            client = get_redis_client()
            self._redis = client.sync if client else None
        return self._redis
    
    def _fetch_truth_ticks(self, symbols: List[str]) -> Dict[str, List[Dict]]:
        """
        Fetch truth ticks from Redis (inspect keys) with venue filtering.
        
        Returns dict: {symbol: [ {ts, price, size, venue}, ... ]} sorted by ts.
        FNRA: only 100/200 | Others: ≥15 lot
        """
        result = {}
        redis = self._get_redis()
        if not redis:
            return result
        
        for symbol in symbols:
            try:
                key = f"truth_ticks:inspect:{symbol}"
                raw = redis.get(key)
                if not raw:
                    continue
                if isinstance(raw, bytes):
                    raw = raw.decode('utf-8')
                
                data = json.loads(raw)
                path_data = data.get('data', {}).get('path_dataset', [])
                if not path_data:
                    continue
                
                filtered = []
                for t in path_data:
                    venue = t.get('venue', '')
                    size = t.get('size', 0)
                    
                    # FNRA filter: only 100 or 200
                    if venue == FNRA_VENUE:
                        if size not in FNRA_VALID_SIZES:
                            continue
                    else:
                        # Non-FNRA: must be ≥15
                        if size < NON_FNRA_MIN_SIZE:
                            continue
                    
                    price = t.get('price', 0)
                    if price <= 0:
                        continue
                    
                    filtered.append({
                        'ts': t.get('timestamp', 0),
                        'price': price,
                        'size': size,
                        'venue': venue,
                    })
                
                if filtered:
                    result[symbol] = sorted(filtered, key=lambda x: x['ts'])
            
            except Exception as e:
                logger.debug(f"[{self.ENGINE_NAME}] Tick fetch err {symbol}: {e}")
        
        return result
    
    # =====================================================================
    # TICK ANALYSIS
    # =====================================================================
    
    def _get_state(self, symbol: str, account_id: str = '') -> SymbolTickState:
        """Get per-symbol, per-account state. Key = '{account_id}:{symbol}'."""
        key = f"{account_id}:{symbol}" if account_id else symbol
        if key not in self._states:
            self._states[key] = SymbolTickState()
        return self._states[key]
    
    def _update_tick_state(self, symbol: str, ticks: List[Dict], account_id: str = '') -> SymbolTickState:
        """
        Process truth ticks and update consecutive direction counters.
        
        Real tick = price change ≥ MIN_TICK_SIZE ($0.05)
        Consecutive counter resets on:
          - opposite direction
          - change < MIN_TICK_SIZE (noise)
        """
        state = self._get_state(symbol, account_id)
        
        if not ticks or len(ticks) < 2:
            return state
        
        for i in range(1, len(ticks)):
            prev_p = ticks[i-1]['price']
            curr_p = ticks[i]['price']
            dp = curr_p - prev_p
            
            if dp <= -MIN_TICK_SIZE_FLOOR:
                # REAL downtick (≥5c drop)
                state.consec_down += 1
                state.consec_up = 0
                state.last_direction = 'DOWN'
                state.last_valid_price = curr_p
                state.last_tick_ts = ticks[i]['ts']
                state.last_tick_delta = dp
            
            elif dp >= MIN_TICK_SIZE_FLOOR:
                # REAL uptick (≥5c rise)
                state.consec_up += 1
                state.consec_down = 0
                state.last_direction = 'UP'
                state.last_valid_price = curr_p
                state.last_tick_ts = ticks[i]['ts']
                state.last_tick_delta = dp
            
            else:
                # Small move = noise → reset both
                state.consec_down = 0
                state.consec_up = 0
            
            state.last_valid_price = curr_p
        
        return state
    
    # =====================================================================
    # ORDER TAG RESOLUTION
    # =====================================================================
    
    def _resolve_order_subtype(self, action: str, current_qty: float) -> str:
        """
        Resolve MM_NEWC order subtype tag.
        
        Format: MM_NEWC_{LONG|SHORT}_{INC|DEC}
        """
        # Determine position side
        if abs(current_qty) < 0.001:
            side = "LONG" if action == "BUY" else "SHORT"
        else:
            side = "LONG" if current_qty > 0 else "SHORT"
        
        # Determine INC/DEC
        if side == "LONG":
            direction = "INC" if action == "BUY" else "DEC"
        else:  # SHORT
            direction = "INC" if action == "SELL" else "DEC"
        
        return f"MM_NEWC_{side}_{direction}"
    
    # =====================================================================
    # SIGNAL GENERATION
    # =====================================================================
    
    def _should_signal_buy(
        self, state: SymbolTickState, bid: float, ask: float
    ) -> Optional[Dict]:
        """
        Check if we should generate a BUY signal.
        Uses DYNAMIC config based on actual spread.
        
        Conditions:
          1. Last real tick was DOWN (≥5c)
          2. Tick size >= dynamic min_tick for this spread
          3. Consecutive count >= dynamic min_consec
          4. No active NEWC long
          5. Cooldown OK
          6. Spread >= MIN_SPREAD_FLOOR
        """
        now = time.time()
        spread = ask - bid
        
        if spread < MIN_SPREAD_FLOOR:
            return None
        
        if state.last_direction != 'DOWN' or state.consec_down < 1:
            return None
        
        if state.long_entry_price > 0:
            return None  # Already in a NEWC long
        
        if now - state.last_buy_signal_ts < COOLDOWN_SECONDS:
            return None
        
        # Get dynamic config for THIS spread
        cfg = get_dynamic_config(spread)
        min_tick = cfg['min_tick']
        profit_target = cfg['profit_target']
        entry_offset = cfg['entry_offset']
        min_consec = cfg['min_consec']
        strategy_name = cfg['strategy_name']
        
        # Check tick size meets dynamic minimum
        last_tick_abs = abs(state.last_tick_delta) if state.last_tick_delta else 0
        if last_tick_abs < min_tick:
            return None  # Tick too small for this spread category
        
        # Check consecutive count meets dynamic minimum
        if state.consec_down < min_consec:
            return None  # Not enough consecutive ticks
        
        is_strong = state.consec_down >= CONSEC_STRONG
        entry_price = round(bid + spread * entry_offset, 4)
        
        return {
            'action': 'BUY',
            'entry_price': entry_price,
            'is_strong': is_strong,
            'consec': state.consec_down,
            'lot_mult': CONSEC_LOT_MULT if is_strong else 1.0,
            'spread': spread,
            'profit_target': profit_target,
            'strategy_name': strategy_name,
            'tick_size_cents': last_tick_abs * 100,
            'reason': (
                f"NEWC BUY [{strategy_name}]: {state.consec_down}×DT (≥{min_tick*100:.0f}c) "
                f"{'\u2605STRONG ' if is_strong else ''}"
                f"entry={entry_price:.2f} "
                f"[bid={bid:.2f}+{spread*entry_offset*100:.0f}c] "
                f"spread={spread*100:.0f}c "
                f"tgt=+{profit_target*100:.0f}c"
            ),
        }
    
    def _should_signal_short(
        self, state: SymbolTickState, bid: float, ask: float
    ) -> Optional[Dict]:
        """
        Check if we should generate a SHORT signal.
        Uses DYNAMIC config based on actual spread.
        
        Conditions:
          1. Last real tick was UP (≥5c)
          2. Tick size >= dynamic min_tick for this spread
          3. Consecutive count >= dynamic min_consec
          4. No active NEWC short
          5. Cooldown OK
          6. Spread >= MIN_SPREAD_FLOOR
        """
        now = time.time()
        spread = ask - bid
        
        if spread < MIN_SPREAD_FLOOR:
            return None
        
        if state.last_direction != 'UP' or state.consec_up < 1:
            return None
        
        if state.short_entry_price > 0:
            return None  # Already in a NEWC short
        
        if now - state.last_short_signal_ts < COOLDOWN_SECONDS:
            return None
        
        # Get dynamic config for THIS spread
        cfg = get_dynamic_config(spread)
        min_tick = cfg['min_tick']
        profit_target = cfg['profit_target']
        entry_offset = cfg['entry_offset']
        min_consec = cfg['min_consec']
        strategy_name = cfg['strategy_name']
        
        # Check tick size meets dynamic minimum
        last_tick_abs = abs(state.last_tick_delta) if state.last_tick_delta else 0
        if last_tick_abs < min_tick:
            return None
        
        # Check consecutive count meets dynamic minimum
        if state.consec_up < min_consec:
            return None
        
        is_strong = state.consec_up >= CONSEC_STRONG
        entry_price = round(ask - spread * entry_offset, 4)
        
        return {
            'action': 'SELL',
            'entry_price': entry_price,
            'is_strong': is_strong,
            'consec': state.consec_up,
            'lot_mult': CONSEC_LOT_MULT if is_strong else 1.0,
            'spread': spread,
            'profit_target': profit_target,
            'strategy_name': strategy_name,
            'tick_size_cents': last_tick_abs * 100,
            'reason': (
                f"NEWC SHORT [{strategy_name}]: {state.consec_up}×UT (≥{min_tick*100:.0f}c) "
                f"{'\u2605STRONG ' if is_strong else ''}"
                f"entry={entry_price:.2f} "
                f"[ask={ask:.2f}-{spread*entry_offset*100:.0f}c] "
                f"spread={spread*100:.0f}c "
                f"tgt=+{profit_target*100:.0f}c"
            ),
        }
    
    def _should_take_profit_long(
        self, state: SymbolTickState, bid: float, ask: float,
        ticks: List[Dict] = None,
    ) -> Optional[Dict]:
        """
        Check if active NEWC long should take profit.
        
        QUICK PROFIT via Truth Tick Frontrunning:
          - Check every truth tick: does it give us ≥7c profit?
          - If tick_price >= fill + 8c → SELL @ tick_price - 1c (frontrun)
          - This guarantees ≥7c profit per trade
          - We don't wait for full dynamic target (25c etc)
          - Quick turnover = less risk, more cycles
        
        Fallback: L1 ask check for full dynamic target
        """
        if state.fill_price_long <= 0:
            return None
        if state.profit_order_sent_long:
            return None
        
        fill = state.fill_price_long
        # Full dynamic target (ideal exit) — used for L1 check
        profit_target = max(state.profit_target_long, MIN_PROFIT_TARGET_FLOOR)
        full_target_price = fill + profit_target
        spread = ask - bid
        cfg = get_dynamic_config(spread)
        entry_offset = cfg['entry_offset']
        
        # ═══ METHOD 1: TRUTH TICK QUICK PROFIT (any tick ≥7c after 1c frontrun) ═══
        # Minimum tick price needed: fill + 7c + 1c = fill + 8c
        # (1c for frontrunning, remaining 7c = minimum profit)
        min_tick_for_profit = fill + MIN_PROFIT_TARGET_FLOOR + 0.01
        
        if ticks:
            # Check most recent ticks first (freshest price)
            best_tick = None
            best_tick_price = 0
            for t in reversed(ticks):
                tick_price = t.get('price', 0)
                if tick_price >= min_tick_for_profit:
                    # This tick gives us ≥7c profit with 1c frontrun!
                    if tick_price > best_tick_price:
                        best_tick = t
                        best_tick_price = tick_price
            
            if best_tick:
                tick_price = best_tick_price
                # Frontrun: sell 1c below the tick print
                exit_price = round(tick_price - 0.01, 4)
                pnl_c = (exit_price - fill) * 100
                venue = best_tick.get('venue', '')
                return {
                    'action': 'SELL',
                    'entry_price': exit_price,
                    'is_strong': False,
                    'consec': 0,
                    'lot_mult': 1.0,
                    'spread': spread,
                    'is_profit_take': True,
                    'pnl_cents': pnl_c,
                    'trigger': 'TICK_FRONTRUN',
                    'trigger_price': tick_price,
                    'venue_hint': venue,
                    'reason': (
                        f"NEWC QUICK PROFIT LONG [{state.strategy_long}]: "
                        f"tick@${tick_price:.2f} ({venue}) → frontrun SELL@${exit_price:.2f} | "
                        f"+{pnl_c:.0f}c (fill=${fill:.2f}+{pnl_c:.0f}c) "
                        f"[min 7c, ideal {profit_target*100:.0f}c]"
                    ),
                }
        
        # ═══ METHOD 2: L1 ASK check (full target or 7c floor) ═══
        # If ask already above our min profit price
        check_price = min(full_target_price, fill + MIN_PROFIT_TARGET_FLOOR)
        if ask >= check_price + 0.02:
            exit_price = round(ask - spread * entry_offset, 4)
            if exit_price >= fill + MIN_PROFIT_TARGET_FLOOR:
                pnl_c = (exit_price - fill) * 100
                return {
                    'action': 'SELL',
                    'entry_price': exit_price,
                    'is_strong': False,
                    'consec': 0,
                    'lot_mult': 1.0,
                    'spread': spread,
                    'is_profit_take': True,
                    'pnl_cents': pnl_c,
                    'trigger': 'L1_ASK',
                    'trigger_price': ask,
                    'reason': (
                        f"NEWC PROFIT LONG [{state.strategy_long}]: "
                        f"ask=${ask:.2f} >= min_tgt=${check_price:.2f} -> "
                        f"SELL@${exit_price:.2f} | +{pnl_c:.0f}c "
                        f"(fill=${fill:.2f})"
                    ),
                }
        
        return None
    
    def _should_take_profit_short(
        self, state: SymbolTickState, bid: float, ask: float,
        ticks: List[Dict] = None,
    ) -> Optional[Dict]:
        """
        Check if active NEWC short should take profit.
        
        QUICK PROFIT via Truth Tick Frontrunning (SHORT side):
          - Check every truth tick: does it give us >=7c profit?
          - If tick_price <= fill - 8c -> BUY(cover) @ tick_price + 1c (frontrun)
          - This guarantees >=7c profit per trade
          - Quick turnover = less risk, more cycles
        
        Fallback: L1 bid check
        """
        if state.fill_price_short <= 0:
            return None
        if state.profit_order_sent_short:
            return None
        
        fill = state.fill_price_short
        # Full dynamic target (ideal exit)
        profit_target = max(state.profit_target_short, MIN_PROFIT_TARGET_FLOOR)
        full_target_price = fill - profit_target
        spread = ask - bid
        cfg = get_dynamic_config(spread)
        entry_offset = cfg['entry_offset']
        
        # === METHOD 1: TRUTH TICK QUICK PROFIT (any tick >=7c after 1c frontrun) ===
        # Maximum tick price for profit: fill - 7c - 1c = fill - 8c
        max_tick_for_profit = fill - MIN_PROFIT_TARGET_FLOOR - 0.01
        
        if ticks:
            best_tick = None
            best_tick_price = float('inf')
            for t in reversed(ticks):
                tick_price = t.get('price', 0)
                if tick_price > 0 and tick_price <= max_tick_for_profit:
                    if tick_price < best_tick_price:
                        best_tick = t
                        best_tick_price = tick_price
            
            if best_tick:
                tick_price = best_tick_price
                exit_price = round(tick_price + 0.01, 4)
                pnl_c = (fill - exit_price) * 100
                venue = best_tick.get('venue', '')
                return {
                    'action': 'BUY',
                    'entry_price': exit_price,
                    'is_strong': False,
                    'consec': 0,
                    'lot_mult': 1.0,
                    'spread': spread,
                    'is_profit_take': True,
                    'pnl_cents': pnl_c,
                    'trigger': 'TICK_FRONTRUN',
                    'trigger_price': tick_price,
                    'venue_hint': venue,
                    'reason': (
                        f"NEWC QUICK PROFIT SHORT [{state.strategy_short}]: "
                        f"tick@${tick_price:.2f} ({venue}) -> frontrun BUY@${exit_price:.2f} | "
                        f"+{pnl_c:.0f}c (fill=${fill:.2f}-{pnl_c:.0f}c) "
                        f"[min 7c, ideal {profit_target*100:.0f}c]"
                    ),
                }
        
        # === METHOD 2: L1 BID check (7c floor) ===
        check_price = max(full_target_price, fill - MIN_PROFIT_TARGET_FLOOR)
        if bid <= check_price - 0.02:
            exit_price = round(bid + spread * entry_offset, 4)
            if exit_price <= fill - MIN_PROFIT_TARGET_FLOOR:
                pnl_c = (fill - exit_price) * 100
                return {
                    'action': 'BUY',
                    'entry_price': exit_price,
                    'is_strong': False,
                    'consec': 0,
                    'lot_mult': 1.0,
                    'spread': spread,
                    'is_profit_take': True,
                    'pnl_cents': pnl_c,
                    'trigger': 'L1_BID',
                    'trigger_price': bid,
                    'reason': (
                        f"NEWC PROFIT SHORT [{state.strategy_short}]: "
                        f"bid=${bid:.2f} <= min_tgt=${check_price:.2f} -> "
                        f"BUY@${exit_price:.2f} | +{pnl_c:.0f}c "
                        f"(fill=${fill:.2f})"
                    ),
                }
        
        return None
    
    # =====================================================================
    # SIGNAL SCORING (for ranking candidates)
    # =====================================================================
    
    @staticmethod
    def _score_signal(
        tick_size_cents: float,
        consec: int,
        spread_cents: float,
        is_strong: bool,
    ) -> float:
        """
        Score an entry signal for ranking.
        Higher = better opportunity.
        
        Components:
          - tick_size:  ×2 weight (10c tick = 20pts, 5c = 10pts)
          - consec:     ×15 per consecutive tick (3-consec = 45pts bonus)
          - spread:     ×1 (wider = more room)
          - STRONG:     +20 flat bonus for 3+ consecutive
        """
        score = 0.0
        score += tick_size_cents * 2.0      # 5c→10, 10c→20, 20c→40
        score += consec * 15.0              # 1→15, 3→45, 5→75
        score += spread_cents * 1.0         # 6c→6, 15c→15
        if is_strong:
            score += 20.0                   # 3-consec bonus
        return round(score, 1)
    
    # =====================================================================
    # MAIN RUN (called from RUNALL cycle)
    # =====================================================================
    
    async def run(self, request: DecisionRequest) -> List[Decision]:
        """
        NEWCLMM main decision loop.
        
        Called by RUNALL orchestrator each cycle.
        
        Flow:
          1. Fetch truth ticks for all visible symbols
          2. FNRA-filter ticks (100/200 only from FNRA)
          3. Update consecutive tick counters per symbol
          4. Check profit targets on active NEWC positions
          5. Generate new entry signals (BUY on DT, SHORT on UT)
          6. Return Decision objects with MM_NEWC tags
        """
        decisions = []
        paper_decisions = []  # For paper mode logging
        
        # Check enabled state (sync from Redis each cycle)
        self.sync_enabled_from_redis()
        is_paper = not self._enabled  # PAPER mode when disabled
        
        # Gather symbols — split into priority and others
        all_symbols = list(set(request.l1_data.keys()))
        if request.available_symbols:
            for s in request.available_symbols:
                if s not in all_symbols:
                    all_symbols.append(s)
        
        priority_syms = [s for s in all_symbols if s in PRIORITY_SYMBOLS]
        other_syms = [s for s in all_symbols if s not in PRIORITY_SYMBOLS]
        
        # Free exposure gate
        free_exp_engine = get_free_exposure_engine()
        try:
            from app.trading.trading_account_context import get_trading_context
            ctx = get_trading_context()
            account_id = ctx.trading_mode.value if ctx else None
        except Exception:
            account_id = None
        
        free_snap = free_exp_engine.get_cached_snapshot(account_id) if account_id else None
        if free_snap and free_snap.get('blocked'):
            logger.warning(f"[{self.ENGINE_NAME}] FREE EXPOSURE BLOCKED -- skip all")
            return decisions
        
        # Fetch truth ticks for ALL symbols (priority + others)
        all_ticks = self._fetch_truth_ticks(all_symbols)
        
        # Count active NEWC positions (for MAX_ACTIVE_NEWC limit)
        active_count = sum(
            1 for s in self._states.values()
            if s.long_entry_price > 0 or s.short_entry_price > 0
        )
        remaining_slots = max(0, MAX_ACTIVE_NEWC - active_count)
        
        # ===============================================================
        # PRIORITY-FIRST SCANNING
        # 
        # 1. Always process profit-take for ALL symbols (priority + others)
        # 2. Scan PRIORITY symbols first for entry candidates
        # 3. If >= MIN_PRIORITY_SIGNALS (15) found, skip others
        # 4. If < 15, also scan other symbols
        # 5. Priority symbols get +25 score bonus in ranking
        # ===============================================================
        
        profit_take_decisions = []  # Always processed (all symbols)
        entry_candidates = []       # (score, side, Decision, symbol, signal, state)
        
        # Determine which symbol sets to scan for entries
        # Always scan priority first; conditionally scan others
        symbols_for_entries = list(priority_syms)  # Start with priority
        scan_others = True  # Will be set to False if enough priority signals
        
        # Process ALL symbols for profit-take + priority symbols for entries
        for symbol in all_symbols:
            try:
                # L1 data
                l1 = request.l1_data.get(symbol)
                if not isinstance(l1, dict):
                    continue
                
                bid = l1.get('bid', 0)
                ask = l1.get('ask', 0)
                if not bid or not ask or bid <= 0 or ask <= 0:
                    continue
                
                spread = ask - bid
                
                # Update tick state
                ticks = all_ticks.get(symbol, [])
                state = self._update_tick_state(symbol, ticks, account_id=account_id or '')
                
                # Check pending broker orders
                pos = next((p for p in request.positions if p.symbol == symbol), None)
                has_pending_buy = False
                has_pending_sell = False
                current_qty = 0.0
                if pos:
                    current_qty = pos.qty
                    pot_qty = getattr(pos, 'potential_qty', pos.qty) or pos.qty
                    if pot_qty > pos.qty:
                        has_pending_buy = True
                    elif pot_qty < pos.qty:
                        has_pending_sell = True
                
                # Helper: calculate lot with MIN_LOT floor
                def _calc_lot(base_lot, mult=1.0):
                    raw = int(base_lot * mult)
                    return max(raw, MIN_LOT) if raw > 0 else 0
                
                # ── PHASE 1: PROFIT TAKE (always, no limit) ──
                
                profit_long = self._should_take_profit_long(state, bid, ask, ticks=ticks)
                if profit_long and not has_pending_sell:
                    tag = self._resolve_order_subtype('SELL', current_qty)
                    base_lot = free_exp_engine.get_mm_lot_sync(account_id, symbol) if account_id else MIN_LOT
                    lot = _calc_lot(base_lot)
                    if lot > 0:
                        dec = Decision(
                            symbol=symbol,
                            action='SELL',
                            order_type=ORDER_TYPE,
                            calculated_lot=lot,
                            price_hint=profit_long['entry_price'],
                            strategy_tag=tag,
                            reason=profit_long['reason'],
                            confidence=0.95,
                            priority=self.PRIORITY,
                            engine_name=self.ENGINE_NAME,
                            metrics_used={
                                'signal': 'PROFIT_TAKE_LONG',
                                'pnl_cents': profit_long.get('pnl_cents', 0),
                                'fill_price': state.fill_price_long,
                                'exit': profit_long['entry_price'],
                                'trigger': profit_long.get('trigger', ''),
                                'venue_hint': profit_long.get('venue_hint', ''),
                                'spread': spread,
                                'bid': bid,
                                'ask': ask,
                                'hidden': HIDDEN,
                                'pos_tag': self.POS_TAG,
                                'engine_tag': self.ENGINE_TAG,
                                'is_priority': symbol in PRIORITY_SYMBOLS,
                            }
                        )
                        profit_take_decisions.append(dec)
                        state.profit_order_sent_long = True
                        state.trades_today += 1
                        _tp_pnl = profit_long.get('pnl_cents', 0)
                        _pri = '[PRI]' if symbol in PRIORITY_SYMBOLS else '[OTH]'
                        if is_paper:
                            # In paper mode, simulate the fill completion
                            state.pnl_today_cents += _tp_pnl
                            state.wins_today += 1
                            state.long_entry_price = 0.0
                            state.fill_price_long = 0.0
                            state.profit_order_sent_long = False
                            logger.warning(
                                f"[NEWC PAPER] 📋 TP LONG {_pri} {symbol} {lot}lot "
                                f"SELL@${profit_long['entry_price']:.2f} HIDDEN "
                                f"| PFF@${state.fill_price_long:.2f} PnL={_tp_pnl:+.0f}c "
                                f"| trigger={profit_long.get('trigger','')} "
                                f"venue={profit_long.get('venue_hint','')} "
                                f"| bid=${bid:.2f} ask=${ask:.2f} spr={spread*100:.0f}c "
                                f"| tag={tag}"
                            )
                        else:
                            logger.warning(
                                f"[{self.ENGINE_NAME}] TP LONG {_pri} {symbol} {lot}lot "
                                f"SELL@${profit_long['entry_price']:.2f} HIDDEN "
                                f"| PFF@${state.fill_price_long:.2f} PnL={_tp_pnl:+.0f}c "
                                f"| trigger={profit_long.get('trigger','')} "
                                f"venue={profit_long.get('venue_hint','')} "
                                f"| bid=${bid:.2f} ask=${ask:.2f} spr={spread*100:.0f}c "
                                f"| tag={tag}"
                            )
                
                profit_short = self._should_take_profit_short(state, bid, ask, ticks=ticks)
                if profit_short and not has_pending_buy:
                    tag = self._resolve_order_subtype('BUY', current_qty)
                    base_lot = free_exp_engine.get_mm_lot_sync(account_id, symbol) if account_id else MIN_LOT
                    lot = _calc_lot(base_lot)
                    if lot > 0:
                        dec = Decision(
                            symbol=symbol,
                            action='BUY',
                            order_type=ORDER_TYPE,
                            calculated_lot=lot,
                            price_hint=profit_short['entry_price'],
                            strategy_tag=tag,
                            reason=profit_short['reason'],
                            confidence=0.95,
                            priority=self.PRIORITY,
                            engine_name=self.ENGINE_NAME,
                            metrics_used={
                                'signal': 'PROFIT_TAKE_SHORT',
                                'pnl_cents': profit_short.get('pnl_cents', 0),
                                'fill_price': state.fill_price_short,
                                'exit': profit_short['entry_price'],
                                'trigger': profit_short.get('trigger', ''),
                                'venue_hint': profit_short.get('venue_hint', ''),
                                'spread': spread,
                                'bid': bid,
                                'ask': ask,
                                'hidden': HIDDEN,
                                'pos_tag': self.POS_TAG,
                                'engine_tag': self.ENGINE_TAG,
                                'is_priority': symbol in PRIORITY_SYMBOLS,
                            }
                        )
                        profit_take_decisions.append(dec)
                        state.profit_order_sent_short = True
                        state.trades_today += 1
                        _tp_pnl = profit_short.get('pnl_cents', 0)
                        _pri = '[PRI]' if symbol in PRIORITY_SYMBOLS else '[OTH]'
                        if is_paper:
                            state.pnl_today_cents += _tp_pnl
                            state.wins_today += 1
                            state.short_entry_price = 0.0
                            state.fill_price_short = 0.0
                            state.profit_order_sent_short = False
                            logger.warning(
                                f"[NEWC PAPER] 📋 TP SHORT {_pri} {symbol} {lot}lot "
                                f"BUY@${profit_short['entry_price']:.2f} HIDDEN "
                                f"| PFF@${state.fill_price_short:.2f} PnL={_tp_pnl:+.0f}c "
                                f"| trigger={profit_short.get('trigger','')} "
                                f"venue={profit_short.get('venue_hint','')} "
                                f"| bid=${bid:.2f} ask=${ask:.2f} spr={spread*100:.0f}c "
                                f"| tag={tag}"
                            )
                        else:
                            logger.warning(
                                f"[{self.ENGINE_NAME}] TP SHORT {_pri} {symbol} {lot}lot "
                                f"BUY@${profit_short['entry_price']:.2f} HIDDEN "
                                f"| PFF@${state.fill_price_short:.2f} PnL={_tp_pnl:+.0f}c "
                                f"| trigger={profit_short.get('trigger','')} "
                                f"venue={profit_short.get('venue_hint','')} "
                                f"| bid=${bid:.2f} ask=${ask:.2f} spr={spread*100:.0f}c "
                                f"| tag={tag}"
                            )
                
                # -- PHASE 2: NEW ENTRY CANDIDATES (priority-gated) --
                # Only generate entries for symbols in the current scan set
                is_priority = symbol in PRIORITY_SYMBOLS
                if not is_priority and not scan_others:
                    continue  # Skip non-priority if we have enough signals
                
                # BUY signal (downtick detected)
                buy_sig = self._should_signal_buy(state, bid, ask)
                if buy_sig and not has_pending_buy:
                    tag = self._resolve_order_subtype('BUY', current_qty)
                    base_lot = free_exp_engine.get_mm_lot_sync(account_id, symbol) if account_id else MIN_LOT
                    lot = _calc_lot(base_lot, buy_sig['lot_mult'])
                    if lot > 0:
                        score = self._score_signal(
                            tick_size_cents=buy_sig.get('tick_size_cents', 5),
                            consec=buy_sig['consec'],
                            spread_cents=spread * 100,
                            is_strong=buy_sig['is_strong'],
                        )
                        # Priority symbols get score bonus
                        if is_priority:
                            score += PRIORITY_SCORE_BONUS
                        
                        dec = Decision(
                            symbol=symbol,
                            action='BUY',
                            order_type=ORDER_TYPE,
                            calculated_lot=lot,
                            price_hint=buy_sig['entry_price'],
                            strategy_tag=tag,
                            reason=buy_sig['reason'],
                            confidence=0.95 if buy_sig['is_strong'] else 0.85,
                            priority=self.PRIORITY,
                            engine_name=self.ENGINE_NAME,
                            metrics_used={
                                'signal': 'STRONG_BUY' if buy_sig['is_strong'] else 'BUY',
                                'consec_down': buy_sig['consec'],
                                'entry_price': buy_sig['entry_price'],
                                'spread': spread,
                                'hidden': HIDDEN,
                                'profit_target': buy_sig.get('profit_target', MIN_PROFIT_TARGET_FLOOR),
                                'strategy': buy_sig.get('strategy_name', ''),
                                'lot_mult': buy_sig['lot_mult'],
                                'score': score,
                                'is_priority': is_priority,
                                'pos_tag': self.POS_TAG,
                                'engine_tag': self.ENGINE_TAG,
                            }
                        )
                        entry_candidates.append((score, 'BUY', dec, symbol, buy_sig, state))
                
                # SHORT signal (uptick detected)
                short_sig = self._should_signal_short(state, bid, ask)
                if short_sig and not has_pending_sell:
                    tag = self._resolve_order_subtype('SELL', current_qty)
                    base_lot = free_exp_engine.get_mm_lot_sync(account_id, symbol) if account_id else MIN_LOT
                    lot = _calc_lot(base_lot, short_sig['lot_mult'])
                    if lot > 0:
                        score = self._score_signal(
                            tick_size_cents=short_sig.get('tick_size_cents', 5),
                            consec=short_sig['consec'],
                            spread_cents=spread * 100,
                            is_strong=short_sig['is_strong'],
                        )
                        if is_priority:
                            score += PRIORITY_SCORE_BONUS
                        
                        dec = Decision(
                            symbol=symbol,
                            action='SELL',
                            order_type=ORDER_TYPE,
                            calculated_lot=lot,
                            price_hint=short_sig['entry_price'],
                            strategy_tag=tag,
                            reason=short_sig['reason'],
                            confidence=0.95 if short_sig['is_strong'] else 0.85,
                            priority=self.PRIORITY,
                            engine_name=self.ENGINE_NAME,
                            metrics_used={
                                'signal': 'STRONG_SHORT' if short_sig['is_strong'] else 'SHORT',
                                'consec_up': short_sig['consec'],
                                'entry_price': short_sig['entry_price'],
                                'spread': spread,
                                'hidden': HIDDEN,
                                'profit_target': short_sig.get('profit_target', MIN_PROFIT_TARGET_FLOOR),
                                'strategy': short_sig.get('strategy_name', ''),
                                'lot_mult': short_sig['lot_mult'],
                                'score': score,
                                'is_priority': is_priority,
                                'pos_tag': self.POS_TAG,
                                'engine_tag': self.ENGINE_TAG,
                            }
                        )
                        entry_candidates.append((score, 'SELL', dec, symbol, short_sig, state))
            
            except Exception as e:
                logger.error(f"[{self.ENGINE_NAME}] Error processing {symbol}: {e}")
        
        # Check if we need to scan non-priority symbols
        priority_entries = [c for c in entry_candidates if c[3] in PRIORITY_SYMBOLS]
        if len(priority_entries) < MIN_PRIORITY_SIGNALS and other_syms:
            # Not enough priority signals — also already scanned others (scan_others=True)
            logger.info(
                f"[{self.ENGINE_NAME}] Priority signals: {len(priority_entries)} "
                f"(< {MIN_PRIORITY_SIGNALS}), including {len(other_syms)} non-priority symbols"
            )
        elif len(priority_entries) >= MIN_PRIORITY_SIGNALS:
            # Enough priority signals — remove non-priority entries
            entry_candidates = priority_entries
            logger.info(
                f"[{self.ENGINE_NAME}] Priority signals: {len(priority_entries)} "
                f"(>= {MIN_PRIORITY_SIGNALS}), skipping non-priority"
            )
        
        # ===============================================================
        # PASS 2: RANK candidates by score, select top N
        # Priority symbols already have +25 score bonus
        # ===============================================================
        
        # Sort by score descending
        entry_candidates.sort(key=lambda x: x[0], reverse=True)
        
        # Log all candidates (for paper mode visibility)
        if entry_candidates:
            logger.info(
                f"[{self.ENGINE_NAME}] {len(entry_candidates)} entry candidates found, "
                f"{remaining_slots} slots available"
            )
        
        # Select top N
        selected_entries = entry_candidates[:remaining_slots]
        rejected_entries = entry_candidates[remaining_slots:]
        
        if rejected_entries:
            for score, side, dec, sym, sig, st in rejected_entries:
                logger.info(
                    f"[{self.ENGINE_NAME}] REJECTED (slot full): {side} {sym} "
                    f"score={score:.1f} consec={sig['consec']}"
                )
        
        # Process selected entries
        for score, side, dec, sym, sig, st in selected_entries:
            _pri = '[PRI]' if sym in PRIORITY_SYMBOLS else '[OTH]'
            _spr = dec.metrics_used.get('spread', 0) * 100
            _strat = sig.get('strategy_name', '')
            _consec = sig['consec']
            _tick_c = sig.get('tick_size_cents', 0)
            _entry_log = (
                f"ENTRY {side} {_pri} {sym} {dec.calculated_lot}lot "
                f"@${dec.price_hint:.2f} HIDDEN | score={score:.1f} "
                f"| {_consec}×tick({_tick_c:.0f}c) spr={_spr:.0f}c "
                f"| strat={_strat} | tag={dec.strategy_tag}"
            )
            if is_paper:
                paper_decisions.append(dec)
                logger.warning(f"[NEWC PAPER] 📋 {_entry_log}")
            else:
                decisions.append(dec)
                logger.warning(f"[{self.ENGINE_NAME}] {_entry_log}")
            # Track entry state + DYNAMIC profit target
            if side == 'BUY':
                st.long_entry_price = sig['entry_price']
                st.long_entry_ts = time.time()
                st.last_buy_signal_ts = time.time()
                st.profit_target_long = sig.get('profit_target', MIN_PROFIT_TARGET_FLOOR)
                st.strategy_long = sig.get('strategy_name', '')
                # In paper mode: simulate immediate fill at entry price
                if is_paper:
                    st.fill_price_long = sig['entry_price']
                    st.profit_order_sent_long = False
            else:
                st.short_entry_price = sig['entry_price']
                st.short_entry_ts = time.time()
                st.last_short_signal_ts = time.time()
                st.profit_target_short = sig.get('profit_target', MIN_PROFIT_TARGET_FLOOR)
                st.strategy_short = sig.get('strategy_name', '')
                if is_paper:
                    st.fill_price_short = sig['entry_price']
                    st.profit_order_sent_short = False
            st.trades_today += 1
        
        # ═══ COMBINE: profit-takes + selected entries ═══
        if not is_paper:
            decisions = profit_take_decisions + decisions
        else:
            paper_decisions = profit_take_decisions + paper_decisions
        
        # ═══ CYCLE SUMMARY (both paper and live) ═══
        # Aggregate daily stats for CURRENT account only
        _acct_prefix = f"{account_id}:" if account_id else ''
        acct_states = [
            s for k, s in self._states.items()
            if k.startswith(_acct_prefix)
        ] if _acct_prefix else list(self._states.values())
        total_pnl = sum(s.pnl_today_cents for s in acct_states)
        total_trades = sum(s.trades_today for s in acct_states)
        total_wins = sum(s.wins_today for s in acct_states)
        active_longs = sum(1 for s in acct_states if s.fill_price_long > 0)
        active_shorts = sum(1 for s in acct_states if s.fill_price_short > 0)
        wr = (total_wins / total_trades * 100) if total_trades > 0 else 0
        
        mode_label = "PAPER" if is_paper else "LIVE"
        acct_label = account_id or "?"
        
        all_decisions = paper_decisions if is_paper else decisions
        tp_count = len(profit_take_decisions)
        entry_count = len(selected_entries)
        pri_count = sum(1 for _, _, _, s, _, _ in selected_entries if s in PRIORITY_SYMBOLS) if selected_entries else 0
        
        logger.warning(
            f"[{self.ENGINE_NAME}] ═══ {mode_label} CYCLE [{acct_label}]: "
            f"{len(all_decisions)} orders ({tp_count}TP + {entry_count}ENTRY "
            f"[{pri_count}pri/{entry_count - pri_count}oth]) | "
            f"active: {active_longs}L/{active_shorts}S | "
            f"day: {total_trades}trades {total_pnl:+.0f}c WR={wr:.0f}% ({total_wins}W)"
            f"{' — NO REAL ORDERS (paper)' if is_paper else ''} ═══"
        )
        
        return decisions
    
    # =====================================================================
    # STATUS / DIAGNOSTICS
    # =====================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Engine status for dashboard / API"""
        active_longs = [(k, st) for k, st in self._states.items() if st.long_entry_price > 0]
        active_shorts = [(k, st) for k, st in self._states.items() if st.short_entry_price > 0]
        total_pnl = sum(st.pnl_today_cents for st in self._states.values())
        total_trades = sum(st.trades_today for st in self._states.values())
        total_wins = sum(st.wins_today for st in self._states.values())
        
        return {
            'engine': self.ENGINE_NAME,
            'pos_tag': self.POS_TAG,
            'engine_tag': self.ENGINE_TAG,
            'config': {
                'mode': 'DYNAMIC (spread-based)',
                'min_tick_floor': MIN_TICK_SIZE_FLOOR,
                'min_profit_floor': MIN_PROFIT_TARGET_FLOOR,
                'min_spread_floor': MIN_SPREAD_FLOOR,
                'wide_spread_profit': 0.12,
                'med_spread_profit': 0.25,
                'narrow_spread_profit': 0.15,
                'consec_strong': CONSEC_STRONG,
                'consec_lot_mult': CONSEC_LOT_MULT,
                'cooldown_sec': COOLDOWN_SECONDS,
                'max_active': MAX_ACTIVE_NEWC,
            },
            'performance': {
                'tracked_symbols': len(self._states),
                'active_longs': len(active_longs),
                'active_shorts': len(active_shorts),
                'total_trades_today': total_trades,
                'total_wins_today': total_wins,
                'total_pnl_today_cents': round(total_pnl, 1),
                'win_rate_today': f"{total_wins/total_trades*100:.0f}%" if total_trades > 0 else "N/A",
            },
            'active_positions': {
                'longs': [
                    {'key': k, 'entry': st.long_entry_price, 'fill': st.fill_price_long,
                     'strategy': st.strategy_long, 'tp_target': st.profit_target_long}
                    for k, st in active_longs
                ],
                'shorts': [
                    {'key': k, 'entry': st.short_entry_price, 'fill': st.fill_price_short,
                     'strategy': st.strategy_short, 'tp_target': st.profit_target_short}
                    for k, st in active_shorts
                ],
            }
        }
    
    def reset_daily(self):
        """Reset daily counters (call at market open)"""
        for state in self._states.values():
            state.trades_today = 0
            state.pnl_today_cents = 0.0
            state.wins_today = 0
            state.long_entry_price = 0.0
            state.short_entry_price = 0.0
        logger.info(f"[{self.ENGINE_NAME}] Daily reset complete")


# ============================================================================
# GLOBAL SINGLETON
# ============================================================================

_newclmm_instance: Optional[NewCLMMEngine] = None


def get_newclmm_engine() -> NewCLMMEngine:
    """Get global NewCLMMEngine instance"""
    global _newclmm_instance
    if _newclmm_instance is None:
        _newclmm_instance = NewCLMMEngine()
    return _newclmm_instance


def initialize_newclmm_engine() -> NewCLMMEngine:
    """Initialize global NewCLMMEngine (fresh instance)"""
    global _newclmm_instance
    _newclmm_instance = NewCLMMEngine()
    return _newclmm_instance
