"""
MM Danger Score Engine
======================

Evaluates MM-originated fills and assigns a DANGER SCORE (0-100)
to determine which MM positions should be reduced/eliminated before market close.

KEY DESIGN: Identifies MM fills via the Strategy TAG in the fill CSV
(MM_ENGINE, GREATEST_MM, SIDEHIT), NOT via intraday position delta.
This is critical because ADDNEWPOS also opens positions intraday (LT),
and those should NOT be subject to MM danger scoring.

Danger Score Components:
  1. GORT Risk        (0-25)  — High absolute GORT = stock drifted from group, risky overnight
  2. FBTOT/THG Risk   (0-25)  — Negative FBTOT or weak FINAL_THG = bad fundamentals 
  3. Spread Risk      (0-20)  — Wide spreads = hard to exit, illiquid
  4. QeBench Risk     (0-15)  — Underperforming benchmark = systematic loser
  5. Close Proximity  (0-15)  — Closer to close = more urgency, score amplified

Exit Strategy (based on Danger Score):
  - 0-30:   SAFE — Hold overnight, no action needed
  - 31-50:  WATCH — Monitor, consider reducing if worsens
  - 51-70:  REDUCE — Place FRONT_SELL/FRONT_BUY orders (truth tick ± $0.01)
  - 71-85:  URGENT — Aggressive front orders, wider tolerance
  - 86-100: EMERGENCY — Last resort: hit BID (for longs) or hit ASK (for shorts)

Prerequisite: Fill tagging must work correctly. Tags flow through:
  - RunAll → order['tag'] → XNL _place_order → strategy_tag
  - Hammer: fire_and_forget → pending_tag → HammerFillsListener → CSV
  - IBKR: orderRef → execDetailsEvent → CSV
"""

import json
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from collections import defaultdict

from app.core.logger import logger


# ═══════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════

# Danger Score thresholds
DANGER_SAFE = 30
DANGER_WATCH = 50
DANGER_REDUCE = 70
DANGER_URGENT = 85
DANGER_EMERGENCY = 100

# Market close time (US Eastern) — 16:00 ET
# We operate in minutes-to-close for the time component
MARKET_CLOSE_HOUR = 16  # ET
MARKET_CLOSE_MIN = 0

# GORT thresholds
GORT_HIGH = 2.0       # Absolute GORT > 2 = significantly away from group
GORT_EXTREME = 3.5    # Absolute GORT > 3.5 = dangerously far from group

# Spread thresholds (as % of price)
SPREAD_TIGHT = 0.003   # < 0.3% = tight, low risk
SPREAD_WIDE = 0.008    # > 0.8% = wide, hard to exit
SPREAD_EXTREME = 0.015 # > 1.5% = very illiquid

# QeBench thresholds (daily change vs benchmark)  
QEBENCH_GOOD = 0.0     # Outperform = positive
QEBENCH_BAD = -0.03    # Underperforming by 3 cents
QEBENCH_TERRIBLE = -0.10  # Underperforming by 10 cents


class MMDangerPosition:
    """Represents a single intraday MM position with its danger assessment."""
    
    def __init__(self, symbol: str, account: str):
        self.symbol = symbol
        self.account = account
        
        # Position data
        self.befday_qty: float = 0       # Start-of-day quantity
        self.current_qty: float = 0       # Current quantity
        self.intraday_delta: float = 0    # MM-added quantity (inferred)
        self.side: str = ""               # LONG or SHORT (of the MM delta)
        self.avg_price: float = 0         # Average fill price if available
        self.current_price: float = 0     # Current market price (last/truth)
        self.unrealized_pnl: float = 0    # PnL on the MM portion
        
        # Market data
        self.bid: float = 0
        self.ask: float = 0
        self.spread: float = 0
        self.spread_pct: float = 0
        self.truth_tick_price: float = 0
        self.truth_tick_age_sec: int = 9999
        
        # Scoring metrics
        self.gort: float = 0
        self.fbtot: float = 0
        self.sfstot: float = 0
        self.final_thg: float = 0
        self.short_final: float = 0
        self.sma63chg: float = 0
        self.daily_chg: float = 0
        self.bench_chg: float = 0
        self.group: str = ""
        
        # QeBench
        self.qe_daily_diff: float = 0  # Position daily change - benchmark daily change
        
        # Danger Score Components
        self.gort_risk: float = 0        # 0-25
        self.fundamental_risk: float = 0  # 0-25
        self.spread_risk: float = 0      # 0-20 
        self.qebench_risk: float = 0     # 0-15
        self.time_urgency: float = 0     # 0-15
        
        # Final
        self.danger_score: float = 0     # 0-100
        self.danger_level: str = "SAFE"  # SAFE/WATCH/REDUCE/URGENT/EMERGENCY
        self.exit_strategy: str = ""     # Recommended exit approach
        self.exit_price: float = 0       # Recommended exit price
        self.notes: List[str] = []       # Human-readable observations


class MMDangerScoreEngine:
    """
    Computes Danger Scores for intraday MM positions.
    
    Usage:
        engine = MMDangerScoreEngine()
        results = engine.scan_all_accounts()
        
        for pos in results:
            if pos.danger_level in ('REDUCE', 'URGENT', 'EMERGENCY'):
                print(f"{pos.symbol}: DANGER={pos.danger_score} -> {pos.exit_strategy}")
    """
    
    def __init__(self):
        self._redis = None
        self._data_fabric = None
        self._static_store = None
    
    def _get_redis(self):
        if not self._redis:
            try:
                from app.core.redis_client import get_redis_client
                client = get_redis_client()
                self._redis = client.sync if client else None
            except Exception:
                pass
        return self._redis
    
    def _get_data_fabric(self):
        if not self._data_fabric:
            try:
                from app.core.data_fabric import get_data_fabric
                self._data_fabric = get_data_fabric()
            except Exception:
                pass
        return self._data_fabric
    
    def _get_static_store(self):
        if not self._static_store:
            try:
                from app.market_data.static_data_store import get_static_store
                self._static_store = get_static_store()
            except Exception:
                pass
        return self._static_store
    
    # ═══════════════════════════════════════════════════════════════
    # CORE: Scan and Score
    # ═══════════════════════════════════════════════════════════════
    
    def scan_all_accounts(self, minutes_to_close: float = None) -> List[MMDangerPosition]:
        """
        Scan all accounts for intraday MM positions and compute danger scores.
        
        Args:
            minutes_to_close: Override for testing. If None, calculated from current time.
            
        Returns:
            List of MMDangerPosition sorted by danger_score descending (most dangerous first)
        """
        if minutes_to_close is None:
            minutes_to_close = self._calculate_minutes_to_close()
        
        all_positions = []
        
        for account_id in self._get_account_ids():
            positions = self._scan_account(account_id, minutes_to_close)
            all_positions.extend(positions)
        
        # Sort by danger score descending
        all_positions.sort(key=lambda p: p.danger_score, reverse=True)
        
        return all_positions
    
    def scan_account(self, account_id: str, minutes_to_close: float = None) -> List[MMDangerPosition]:
        """Scan single account."""
        if minutes_to_close is None:
            minutes_to_close = self._calculate_minutes_to_close()
        
        positions = self._scan_account(account_id, minutes_to_close)
        positions.sort(key=lambda p: p.danger_score, reverse=True)
        return positions
    
    def get_danger_summary(self, minutes_to_close: float = None) -> Dict[str, Any]:
        """
        Get a compact summary of all danger positions.
        Suitable for agent consumption or API response.
        """
        positions = self.scan_all_accounts(minutes_to_close)
        
        if not positions:
            return {
                "timestamp": datetime.now().isoformat(),
                "total_mm_positions": 0,
                "danger_positions": [],
                "summary": "No intraday MM positions detected"
            }
        
        danger_positions = []
        by_level = defaultdict(int)
        
        for pos in positions:
            by_level[pos.danger_level] += 1
            
            danger_positions.append({
                "symbol": pos.symbol,
                "account": pos.account,
                "side": pos.side,
                "mm_qty": int(pos.intraday_delta),
                "danger": round(pos.danger_score, 1),
                "level": pos.danger_level,
                "exit": pos.exit_strategy,
                "exit_price": round(pos.exit_price, 2) if pos.exit_price else None,
                "gort": round(pos.gort, 2),
                "fbtot": round(pos.fbtot, 2),
                "thg": round(pos.final_thg, 1),
                "spread_pct": round(pos.spread_pct * 100, 2),
                "bid": round(pos.bid, 2) if pos.bid else None,
                "ask": round(pos.ask, 2) if pos.ask else None,
                "truth": round(pos.truth_tick_price, 2) if pos.truth_tick_price else None,
                "pnl": round(pos.unrealized_pnl, 2),
                "notes": pos.notes[:3],  # Top 3 observations
                # Component breakdown
                "components": {
                    "gort_risk": round(pos.gort_risk, 1),
                    "fund_risk": round(pos.fundamental_risk, 1),
                    "spread_risk": round(pos.spread_risk, 1),
                    "qe_risk": round(pos.qebench_risk, 1),
                    "time_urgency": round(pos.time_urgency, 1),
                }
            })
        
        return {
            "timestamp": datetime.now().isoformat(),
            "minutes_to_close": round(minutes_to_close or 0, 1),
            "total_mm_positions": len(positions),
            "by_level": dict(by_level),
            "danger_positions": danger_positions,
            "summary": self._generate_summary(positions, by_level)
        }
    
    # ═══════════════════════════════════════════════════════════════
    # INTERNAL: Account scanning — FILL-TAG-BASED (not intraday delta)
    # ═══════════════════════════════════════════════════════════════
    
    # MM tag identifiers — fills with these Strategy tags are considered MM-originated
    MM_TAGS = {"MM_ENGINE", "GREATEST_MM", "SIDEHIT", "MM", "MM_LONG", "MM_SHORT"}
    
    def _scan_account(self, account_id: str, minutes_to_close: float) -> List[MMDangerPosition]:
        """
        Scan a single account for MM-tagged fills and compute danger scores.
        
        KEY DESIGN: We use fill CSV tags (Strategy column) to identify MM fills,
        NOT (current_qty - befday_qty), because ADDNEWPOS also adds positions
        intraday and those are LT, not MM.
        """
        # 1. Get MM fills from today's CSV (filtered by tag)
        mm_fills_by_symbol = self._get_mm_fills_from_store(account_id)
        
        if not mm_fills_by_symbol:
            return []
        
        # 2. Get current positions for avg_price and current_qty context
        current_positions = self._get_current_positions(account_id)
        
        # 3. Build danger positions from MM fills
        mm_positions = []
        for symbol, fill_data in mm_fills_by_symbol.items():
            net_qty = fill_data["net_qty"]
            if abs(net_qty) < 1:
                continue  # MM fills cancel each other out
            
            pos = MMDangerPosition(symbol, account_id)
            pos.intraday_delta = net_qty
            pos.side = "LONG" if net_qty > 0 else "SHORT"
            
            # Fill-level data
            pos.avg_price = fill_data.get("avg_price", 0)
            pos.mm_fill_count = fill_data.get("fill_count", 0)
            pos.mm_tags_seen = fill_data.get("tags_seen", set())
            
            # Current position context (from Redis)
            cur = current_positions.get(symbol, {})
            pos.current_qty = cur.get("qty", 0)
            if pos.avg_price == 0:
                pos.avg_price = cur.get("avg_price", 0)
            
            mm_positions.append(pos)
        
        if not mm_positions:
            return []
        
        # 4. Enrich with market data and metrics
        self._enrich_with_market_data(mm_positions)
        
        # 5. Compute danger scores
        for pos in mm_positions:
            self._compute_danger_score(pos, minutes_to_close)
        
        return mm_positions
    
    def _get_mm_fills_from_store(self, account_id: str) -> Dict[str, Dict]:
        """
        Read today's fill CSV via DailyFillsStore and aggregate only MM-tagged fills.
        
        Returns:
            Dict[symbol] -> {
                "net_qty": float,     # Signed: +BUY / -SELL
                "avg_price": float,   # Volume-weighted average fill price
                "fill_count": int,    # Number of MM fills
                "tags_seen": set,     # Actual tag strings seen
                "total_cost": float,  # For VWAP calculation
                "total_abs_qty": float
            }
        """
        try:
            from app.trading.daily_fills_store import get_daily_fills_store
            store = get_daily_fills_store()
            
            # Map account_id to the CSV account type that DailyFillsStore expects
            fills = store.get_all_fills(account_id)
            
            mm_by_symbol = {}
            
            for fill in fills:
                tag = (fill.get("tag") or "UNKNOWN").upper().strip()
                
                # Only process MM-tagged fills
                if not self._is_mm_tag(tag):
                    continue
                
                symbol = fill.get("symbol", "")
                if not symbol:
                    continue
                
                qty = float(fill.get("qty", 0) or 0)
                price = float(fill.get("price", 0) or 0)
                action = (fill.get("action") or "").upper()
                
                # Sign correction: BUY = positive, SELL = negative
                signed_qty = qty if action == "BUY" else -qty
                
                if symbol not in mm_by_symbol:
                    mm_by_symbol[symbol] = {
                        "net_qty": 0,
                        "total_cost": 0,
                        "total_abs_qty": 0,
                        "fill_count": 0,
                        "tags_seen": set(),
                    }
                
                entry = mm_by_symbol[symbol]
                entry["net_qty"] += signed_qty
                entry["total_cost"] += qty * price
                entry["total_abs_qty"] += qty
                entry["fill_count"] += 1
                entry["tags_seen"].add(tag)
            
            # Calculate VWAP (volume-weighted average price)
            for symbol, entry in mm_by_symbol.items():
                if entry["total_abs_qty"] > 0:
                    entry["avg_price"] = entry["total_cost"] / entry["total_abs_qty"]
                else:
                    entry["avg_price"] = 0
            
            return mm_by_symbol
            
        except Exception as e:
            logger.error(f"[DangerScore] Error reading MM fills for {account_id}: {e}")
            return {}
    
    @classmethod
    def _is_mm_tag(cls, tag: str) -> bool:
        """Check if a fill tag indicates MM origin."""
        tag_upper = tag.upper().strip()
        # Exact match
        if tag_upper in cls.MM_TAGS:
            return True
        # Substring match (e.g., "MM_ENGINE_LONG" would match)
        if "MM" in tag_upper and "LT" not in tag_upper:
            return True
        if "SIDEHIT" in tag_upper:
            return True
        return False
    
    def _get_current_positions(self, account_id: str) -> Dict[str, Dict]:
        """Get current positions from Redis for context (avg_price, current_qty)."""
        redis = self._get_redis()
        if not redis:
            return {}
        
        positions = {}
        try:
            # Try unified positions first
            raw = redis.get(f"psfalgo:unified_positions:{account_id}")
            if not raw:
                raw = redis.get(f"psfalgo:positions:{account_id}")
            
            if raw:
                data = json.loads(raw)
                pos_list = data if isinstance(data, list) else data.get("positions", [])
                for p in pos_list:
                    sym = p.get("symbol") or p.get("Symbol")
                    if sym:
                        qty = float(p.get("quantity", 0) or p.get("Quantity", 0) or 0)
                        avg = float(p.get("avg_price", 0) or p.get("avgCost", 0) or 0)
                        mkt = float(p.get("market_value", 0) or p.get("marketValue", 0) or 0)
                        positions[sym] = {
                            "qty": qty,
                            "avg_price": avg,
                            "market_value": mkt,
                        }
        except Exception as e:
            logger.debug(f"[DangerScore] Error reading positions for {account_id}: {e}")
        
        return positions
    
    def _enrich_with_market_data(self, positions: List[MMDangerPosition]):
        """Enrich positions with current market data, truth ticks, and scoring metrics."""
        fabric = self._get_data_fabric()
        redis = self._get_redis()
        
        for pos in positions:
            symbol = pos.symbol
            
            # DataFabric snapshot (bid/ask/GORT/FBTOT/THG etc.)
            if fabric:
                try:
                    snap = fabric.get_fast_snapshot(symbol)
                    if snap:
                        pos.bid = float(snap.get("bid", 0) or 0)
                        pos.ask = float(snap.get("ask", 0) or 0)
                        pos.current_price = float(snap.get("last", 0) or 0) or pos.bid
                        pos.gort = float(snap.get("GORT", 0) or 0)
                        pos.fbtot = float(snap.get("Fbtot", 0) or 0)
                        pos.sfstot = float(snap.get("SFStot", 0) or 0)
                        pos.final_thg = float(snap.get("FINAL_THG", 0) or 0)
                        pos.short_final = float(snap.get("SHORT_FINAL", 0) or 0)
                        pos.sma63chg = float(snap.get("SMA63chg", 0) or 0)
                        pos.daily_chg = float(snap.get("daily_chg", 0) or 0)
                        pos.bench_chg = float(snap.get("bench_chg", 0) or 0)
                        pos.group = snap.get("GROUP", "")
                        
                        # Spread
                        if pos.bid > 0 and pos.ask > 0:
                            pos.spread = pos.ask - pos.bid
                            mid = (pos.bid + pos.ask) / 2
                            pos.spread_pct = pos.spread / mid if mid > 0 else 0
                except Exception:
                    pass
            
            # Truth tick from canonical source
            if redis:
                try:
                    raw = redis.get(f"tt:ticks:{symbol}")
                    if raw:
                        ticks = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
                        if ticks and isinstance(ticks, list) and len(ticks) > 0:
                            last_tick = ticks[-1]
                            pos.truth_tick_price = float(last_tick.get("price", 0) or 0)
                            ts = float(last_tick.get("ts", 0) or 0)
                            pos.truth_tick_age_sec = int(time.time() - ts) if ts > 0 else 9999
                except Exception:
                    pass
            
            # QeBench diff (daily_chg - bench_chg = how much worse than group)
            pos.qe_daily_diff = pos.daily_chg - pos.bench_chg
            
            # Unrealized PnL on the MM portion
            if pos.avg_price > 0 and pos.current_price > 0:
                if pos.side == "LONG":
                    pos.unrealized_pnl = (pos.current_price - pos.avg_price) * abs(pos.intraday_delta)
                else:
                    pos.unrealized_pnl = (pos.avg_price - pos.current_price) * abs(pos.intraday_delta)
    
    # ═══════════════════════════════════════════════════════════════
    # SCORING ENGINE
    # ═══════════════════════════════════════════════════════════════
    
    def _compute_danger_score(self, pos: MMDangerPosition, minutes_to_close: float):
        """
        Compute the danger score (0-100) for a single position.
        
        Components:
          1. GORT Risk        (0-25)
          2. Fundamental Risk  (0-25) — FBTOT + FINAL_THG combined
          3. Spread Risk       (0-20)
          4. QeBench Risk      (0-15)
          5. Time Urgency      (0-15)
        """
        
        # ── 1. GORT Risk (0-25) ──
        # High absolute GORT = stock is far from group equilibrium = risky overnight
        abs_gort = abs(pos.gort)
        if abs_gort >= GORT_EXTREME:
            pos.gort_risk = 25.0
            pos.notes.append(f"GORT {pos.gort:+.2f} — extreme deviation, mean reversion risk")
        elif abs_gort >= GORT_HIGH:
            # Linear scale: 2.0 -> 12, 3.5 -> 25
            pos.gort_risk = 12 + (abs_gort - GORT_HIGH) / (GORT_EXTREME - GORT_HIGH) * 13
            pos.notes.append(f"GORT {pos.gort:+.2f} — significant deviation from group")
        elif abs_gort >= 1.0:
            pos.gort_risk = abs_gort / GORT_HIGH * 12
        else:
            pos.gort_risk = abs_gort * 3  # Mild: 0-3 points
        
        # Direction matters: If we're LONG and GORT is very positive (stock overvalued vs group),
        # that's MORE dangerous. If LONG and GORT negative, it's less dangerous (room to catch up).
        if pos.side == "LONG" and pos.gort > GORT_HIGH:
            pos.gort_risk = min(25, pos.gort_risk * 1.3)  # 30% bonus danger
            pos.notes.append("LONG + positive GORT — stock already overvalued vs group")
        elif pos.side == "SHORT" and pos.gort < -GORT_HIGH:
            pos.gort_risk = min(25, pos.gort_risk * 1.3)
            pos.notes.append("SHORT + negative GORT — stock already undervalued vs group")
        
        # ── 2. Fundamental Risk (0-25) ──
        # Uses FBTOT (fundamental buy total) and FINAL_THG (overall score)
        # For LONG MM: negative FBTOT = bad sign, low FINAL_THG = risky
        # For SHORT MM: high FBTOT = risky (stock has buying pressure)
        
        if pos.side == "LONG":
            # LONG danger: negative fbtot + low thg = fundamentally weak
            fbtot_score = 0
            if pos.fbtot < -1.0:
                fbtot_score = min(12, abs(pos.fbtot) * 3)
                pos.notes.append(f"FBTOT {pos.fbtot:.2f} — negative fundamentals for long")
            
            thg_score = 0
            if pos.final_thg < 0:
                thg_score = min(13, abs(pos.final_thg) / 10)
                pos.notes.append(f"FINAL_THG {pos.final_thg:.1f} — weak overall score")
            elif pos.final_thg < 20:
                thg_score = (20 - pos.final_thg) / 20 * 5  # Mild risk
                
            pos.fundamental_risk = fbtot_score + thg_score
            
        else:  # SHORT
            # SHORT danger: high fbtot + high thg = stock wants to go up
            fbtot_score = 0
            if pos.fbtot > 1.0:
                fbtot_score = min(12, pos.fbtot * 3)
                pos.notes.append(f"FBTOT {pos.fbtot:.2f} — positive fundamentals against short")
            
            # For shorts we look at SFSTOT / SHORT_FINAL instead
            sf_score = 0
            if pos.sfstot < -1.0:
                sf_score = min(13, abs(pos.sfstot) * 3)
                pos.notes.append(f"SFSTOT {pos.sfstot:.2f} — weak short score")
            elif pos.short_final < 10:
                sf_score = (10 - pos.short_final) / 10 * 5
            
            pos.fundamental_risk = fbtot_score + sf_score
        
        pos.fundamental_risk = min(25, pos.fundamental_risk)
        
        # ── 3. Spread Risk (0-20) ──
        # Wide spreads = hard to exit cleanly = higher danger
        if pos.spread_pct >= SPREAD_EXTREME:
            pos.spread_risk = 20.0
            pos.notes.append(f"Spread {pos.spread_pct*100:.1f}% — very illiquid, exit will cost")
        elif pos.spread_pct >= SPREAD_WIDE:
            pos.spread_risk = 10 + (pos.spread_pct - SPREAD_WIDE) / (SPREAD_EXTREME - SPREAD_WIDE) * 10
            pos.notes.append(f"Spread {pos.spread_pct*100:.1f}% — wide, exit slippage expected")
        elif pos.spread_pct >= SPREAD_TIGHT:
            pos.spread_risk = (pos.spread_pct - SPREAD_TIGHT) / (SPREAD_WIDE - SPREAD_TIGHT) * 10
        else:
            pos.spread_risk = 0
        
        # ── 4. QeBench Risk (0-15) ──
        # Stock underperforming its DOS group benchmark
        qe_diff = pos.qe_daily_diff
        if qe_diff < QEBENCH_TERRIBLE:
            pos.qebench_risk = 15.0
            pos.notes.append(f"QeBench diff {qe_diff:+.3f} — badly underperforming group")
        elif qe_diff < QEBENCH_BAD:
            pos.qebench_risk = 5 + (QEBENCH_BAD - qe_diff) / (QEBENCH_BAD - QEBENCH_TERRIBLE) * 10
        elif qe_diff < QEBENCH_GOOD:
            pos.qebench_risk = abs(qe_diff) / abs(QEBENCH_BAD) * 5
        else:
            pos.qebench_risk = 0  # Outperforming = no risk
        
        # ── 5. Time Urgency (0-15) ──
        # Exponential ramp-up as market close approaches
        if minutes_to_close <= 1:
            pos.time_urgency = 15.0
            pos.notes.append("⏰ LAST MINUTE — maximum urgency")
        elif minutes_to_close <= 5:
            pos.time_urgency = 12 + (5 - minutes_to_close) / 4 * 3
            pos.notes.append(f"⏰ {minutes_to_close:.0f}min to close — high urgency")
        elif minutes_to_close <= 15:
            pos.time_urgency = 6 + (15 - minutes_to_close) / 10 * 6
        elif minutes_to_close <= 30:
            pos.time_urgency = (30 - minutes_to_close) / 15 * 6
        elif minutes_to_close <= 60:
            pos.time_urgency = (60 - minutes_to_close) / 30 * 2
        else:
            pos.time_urgency = 0
        
        # ── TOTAL ──
        pos.danger_score = (
            pos.gort_risk +
            pos.fundamental_risk +
            pos.spread_risk +
            pos.qebench_risk +
            pos.time_urgency
        )
        pos.danger_score = min(100, max(0, pos.danger_score))
        
        # ── Determine level and exit strategy ──
        self._determine_exit_strategy(pos, minutes_to_close)
    
    def _determine_exit_strategy(self, pos: MMDangerPosition, minutes_to_close: float):
        """Determine danger level and recommended exit strategy."""
        score = pos.danger_score
        
        if score <= DANGER_SAFE:
            pos.danger_level = "SAFE"
            pos.exit_strategy = "HOLD — No action needed"
            pos.exit_price = 0
            
        elif score <= DANGER_WATCH:
            pos.danger_level = "WATCH"
            pos.exit_strategy = "MONITOR — Consider reducing if worsens"
            # Suggest front price
            if pos.side == "LONG":
                pos.exit_price = pos.ask - 0.01 if pos.ask > 0 else 0
            else:
                pos.exit_price = pos.bid + 0.01 if pos.bid > 0 else 0
                
        elif score <= DANGER_REDUCE:
            pos.danger_level = "REDUCE"
            # Front-layer: truth tick ± $0.01
            if pos.side == "LONG":
                # Sell: FRONT_SELL at truth_tick - $0.01 (or ask - $0.01)
                base = pos.truth_tick_price if pos.truth_tick_price > 0 else pos.ask
                pos.exit_price = base - 0.01 if base > 0 else 0
                pos.exit_strategy = f"FRONT_SELL @ ${pos.exit_price:.2f} (truth-0.01)"
            else:
                # Cover: FRONT_BUY at truth_tick + $0.01 (or bid + $0.01)
                base = pos.truth_tick_price if pos.truth_tick_price > 0 else pos.bid
                pos.exit_price = base + 0.01 if base > 0 else 0
                pos.exit_strategy = f"FRONT_BUY @ ${pos.exit_price:.2f} (truth+0.01)"
                
        elif score <= DANGER_URGENT:
            pos.danger_level = "URGENT"
            # Aggressive front: wider tolerance
            if pos.side == "LONG":
                base = pos.truth_tick_price if pos.truth_tick_price > 0 else pos.ask
                # More aggressive: 2-3 cents below truth
                pos.exit_price = base - 0.03 if base > 0 else 0
                pos.exit_strategy = f"AGG_FRONT_SELL @ ${pos.exit_price:.2f} (truth-0.03)"
            else:
                base = pos.truth_tick_price if pos.truth_tick_price > 0 else pos.bid
                pos.exit_price = base + 0.03 if base > 0 else 0
                pos.exit_strategy = f"AGG_FRONT_BUY @ ${pos.exit_price:.2f} (truth+0.03)"
                
        else:
            pos.danger_level = "EMERGENCY"
            # Last resort: hit the market
            if pos.side == "LONG":
                # SELL at BID (immediate fill)
                pos.exit_price = pos.bid if pos.bid > 0 else 0
                pos.exit_strategy = f"HIT_BID @ ${pos.exit_price:.2f} — SELL at market bid"
            else:
                # BUY (cover) at ASK (immediate fill)
                pos.exit_price = pos.ask if pos.ask > 0 else 0
                pos.exit_strategy = f"HIT_ASK @ ${pos.exit_price:.2f} — BUY at market ask"
        
        # Special: if time < 1 min and score > WATCH, always escalate
        if minutes_to_close <= 1 and score > DANGER_WATCH:
            if pos.danger_level != "EMERGENCY":
                pos.danger_level = "EMERGENCY"
                if pos.side == "LONG":
                    pos.exit_price = pos.bid if pos.bid > 0 else 0
                    pos.exit_strategy = f"LAST_MIN HIT_BID @ ${pos.exit_price:.2f}"
                else:
                    pos.exit_price = pos.ask if pos.ask > 0 else 0
                    pos.exit_strategy = f"LAST_MIN HIT_ASK @ ${pos.exit_price:.2f}"
                pos.notes.append("⚠️ ESCALATED to EMERGENCY — last minute override")
    
    # ═══════════════════════════════════════════════════════════════
    # UTILITIES
    # ═══════════════════════════════════════════════════════════════
    
    def _get_account_ids(self) -> List[str]:
        """Get active account IDs."""
        redis = self._get_redis()
        if not redis:
            return ["HAMPRO"]
        
        try:
            raw = redis.get("psfalgo:dual_process:state")
            if raw:
                state = json.loads(raw)
                accounts = state.get("accounts", [])
                if accounts:
                    return [a.get("account_id") for a in accounts if a.get("account_id")]
        except Exception:
            pass
        
        return ["HAMPRO", "IBKR_PED", "IBKR_GUN"]
    
    def _calculate_minutes_to_close(self) -> float:
        """Calculate minutes remaining to market close (16:00 ET)."""
        try:
            from datetime import timezone, timedelta
            # US Eastern = UTC-5 (EST) or UTC-4 (EDT)
            # Approximate: use UTC-5 for now
            et_offset = timedelta(hours=-5)
            now_utc = datetime.now(timezone.utc)
            now_et = now_utc + et_offset
            
            close_today = now_et.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MIN, second=0, microsecond=0)
            diff = (close_today - now_et).total_seconds() / 60
            
            return max(0, diff)
        except Exception:
            return 999  # Safe default (market open)
    
    def _generate_summary(self, positions: List[MMDangerPosition], by_level: Dict[str, int]) -> str:
        """Generate human-readable summary."""
        total = len(positions)
        emergency = by_level.get("EMERGENCY", 0)
        urgent = by_level.get("URGENT", 0)
        reduce_count = by_level.get("REDUCE", 0)
        
        if emergency > 0:
            return f"🚨 {emergency} EMERGENCY position(s) need immediate exit! {total} total MM positions."
        elif urgent > 0:
            return f"⚠️ {urgent} URGENT + {reduce_count} REDUCE positions. {total} total MM positions."
        elif reduce_count > 0:
            return f"📉 {reduce_count} position(s) should be reduced. {total} total MM positions."
        else:
            return f"✅ All {total} MM positions are safe. No action needed."


# ═══════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════

_instance = None

def get_mm_danger_engine() -> MMDangerScoreEngine:
    global _instance
    if _instance is None:
        _instance = MMDangerScoreEngine()
    return _instance
