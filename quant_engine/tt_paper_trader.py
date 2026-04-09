"""
QAGENTT LIVE PAPER TRADING AGENT
==================================
Real-time market making paper trader with active learning.

Runs during market hours (9:30 AM - 4:00 PM ET):
- Every 5 minutes scans all MM candidates
- Fetches L1 (bid/ask/last), recent prints, truth ticks
- Places virtual hidden orders: BUY@bid+spread*0.15, SELL@ask-spread*0.15
- Detects fills when truth tick crosses order price
- Tracks paper PnL, positions, fills
- Monitors group behavior, direction, correlations
- End-of-day: sends summary to Claude for learning

Run: python tt_paper_trader.py
"""
import sys, os, json, time, math, logging, asyncio
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from copy import deepcopy

sys.path.insert(0, r"C:\StockTracker\quant_engine")

# Load .env
env_path = os.path.join(r"C:\StockTracker\quant_engine", ".env")
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# ═══════════════ CONFIG ═══════════════
SCAN_INTERVAL_SEC = 300        # 5 minutes
EXPOSURE_TOTAL = 500_000       # $500K total
EXPOSURE_PER_STOCK = 25_000    # $25K per stock
LOT_PCT_OF_ADV = 0.10          # 10% of AVG_ADV
MIN_LOT = 100
MAX_LOT = 3000
MIN_CAPTURE = 0.05             # Min $0.05 per share profit target
SPREAD_ENTRY_PCT = 0.15        # BUY @ bid + spread*15%, SELL @ ask - spread*15%
STOP_LOSS_BPS = 50             # 50 bps stop loss
MAX_HOLD_MINUTES = 60          # Max hold time before force close

# Storage
PAPER_DIR = Path(r"C:\StockTracker\quant_engine\tt_learning\paper_trading")
PAPER_DIR.mkdir(parents=True, exist_ok=True)

# Logging
log_file = PAPER_DIR / "paper_trader.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(log_file), mode="a", encoding="utf-8"),
    ],
)
log = logging.getLogger("PAPER_TRADER")


# ═══════════════ MARKET TIME ═══════════════
def is_market_hours() -> bool:
    """Check if within US market hours (9:30-16:00 ET)."""
    from datetime import timezone
    now_utc = datetime.now(timezone.utc)
    # ET = UTC-5 (EST) or UTC-4 (EDT). Use -5 for simplicity.
    et_hour = (now_utc.hour - 5) % 24
    et_minute = now_utc.minute
    time_val = et_hour * 100 + et_minute
    return 930 <= time_val <= 1600


def get_et_time() -> str:
    """Get current ET time string."""
    from datetime import timezone
    now_utc = datetime.now(timezone.utc)
    et = now_utc - timedelta(hours=5)
    return et.strftime("%H:%M:%S")


# ═══════════════ PAPER PORTFOLIO ═══════════════
class PaperPortfolio:
    """Tracks paper positions, orders, and PnL."""

    def __init__(self):
        self.positions = {}     # {symbol: {qty, avg_price, side, entry_time}}
        self.open_orders = {}   # {symbol: {buys: [...], sells: [...]}}
        self.fills = []         # [{symbol, side, price, qty, time}]
        self.closed_trades = [] # [{symbol, entry_price, exit_price, qty, pnl, hold_time}]
        self.daily_pnl = 0.0
        self.daily_gross = 0.0
        self.daily_fees = 0.0
        self.total_roundtrips = 0
        self.scan_count = 0
        self.opportunities_seen = 0
        self.opportunities_taken = 0

    def place_order(self, symbol, side, price, qty, order_type="hidden"):
        """Place a paper order."""
        if symbol not in self.open_orders:
            self.open_orders[symbol] = {"buys": [], "sells": []}
        order = {
            "price": round(price, 2),
            "qty": qty,
            "type": order_type,
            "time": datetime.now().isoformat(),
            "status": "open",
        }
        if side == "buy":
            self.open_orders[symbol]["buys"].append(order)
        else:
            self.open_orders[symbol]["sells"].append(order)
        return order

    def check_fills(self, symbol, truth_ticks, bid, ask, last_price):
        """Check if any paper orders would have been filled by truth ticks."""
        if symbol not in self.open_orders:
            return []
        
        filled = []
        orders = self.open_orders[symbol]

        for tick in truth_ticks:
            tick_price = tick.get("price", 0)
            tick_size = tick.get("size", 0)
            if tick_price <= 0:
                continue

            # Check buy fills (tick trades at or below our buy price)
            for buy in orders["buys"]:
                if buy["status"] == "open" and tick_price <= buy["price"]:
                    buy["status"] = "filled"
                    buy["fill_price"] = tick_price
                    buy["fill_time"] = datetime.now().isoformat()
                    self._process_fill(symbol, "buy", tick_price, buy["qty"])
                    filled.append(("buy", symbol, tick_price, buy["qty"]))

            # Check sell fills (tick trades at or above our sell price)
            for sell in orders["sells"]:
                if sell["status"] == "open" and tick_price >= sell["price"]:
                    sell["status"] = "filled"
                    sell["fill_price"] = tick_price
                    sell["fill_time"] = datetime.now().isoformat()
                    self._process_fill(symbol, "sell", tick_price, sell["qty"])
                    filled.append(("sell", symbol, tick_price, sell["qty"]))

        # Clean up filled orders
        orders["buys"] = [o for o in orders["buys"] if o["status"] == "open"]
        orders["sells"] = [o for o in orders["sells"] if o["status"] == "open"]

        return filled

    def _process_fill(self, symbol, side, price, qty):
        """Process a fill — open or close position."""
        self.fills.append({
            "symbol": symbol,
            "side": side,
            "price": price,
            "qty": qty,
            "time": datetime.now().isoformat(),
        })

        if symbol in self.positions:
            pos = self.positions[symbol]
            if pos["side"] != side:
                # Closing position — calculate PnL
                close_qty = min(qty, pos["qty"])
                if pos["side"] == "buy":
                    pnl = (price - pos["avg_price"]) * close_qty
                else:
                    pnl = (pos["avg_price"] - price) * close_qty

                # Subtract estimated fees ($0.003/share each way)
                fees = close_qty * 0.003 * 2
                net_pnl = pnl - fees

                self.closed_trades.append({
                    "symbol": symbol,
                    "entry_price": pos["avg_price"],
                    "exit_price": price,
                    "qty": close_qty,
                    "pnl": round(net_pnl, 2),
                    "gross_pnl": round(pnl, 2),
                    "fees": round(fees, 2),
                    "hold_time": (datetime.now() - datetime.fromisoformat(pos["entry_time"])).seconds // 60,
                    "time": datetime.now().isoformat(),
                })

                self.daily_pnl += net_pnl
                self.daily_gross += pnl
                self.daily_fees += fees
                self.total_roundtrips += 1

                pos["qty"] -= close_qty
                if pos["qty"] <= 0:
                    del self.positions[symbol]
                return
        
        # Opening new position
        self.positions[symbol] = {
            "qty": qty,
            "avg_price": price,
            "side": side,
            "entry_time": datetime.now().isoformat(),
        }

    def cancel_all(self, symbol=None):
        """Cancel all open orders for a symbol (or all)."""
        if symbol:
            self.open_orders.pop(symbol, None)
        else:
            self.open_orders.clear()

    def force_close_old(self, current_prices):
        """Force close positions held longer than MAX_HOLD_MINUTES."""
        to_close = []
        for sym, pos in list(self.positions.items()):
            hold_min = (datetime.now() - datetime.fromisoformat(pos["entry_time"])).seconds // 60
            if hold_min >= MAX_HOLD_MINUTES and sym in current_prices:
                to_close.append(sym)

        for sym in to_close:
            pos = self.positions[sym]
            close_price = current_prices[sym]
            close_side = "sell" if pos["side"] == "buy" else "buy"
            self._process_fill(sym, close_side, close_price, pos["qty"])
            log.info(f"  FORCE CLOSE: {sym} {pos['qty']}@{close_price:.2f} (held {MAX_HOLD_MINUTES}+ min)")

    @property
    def summary(self):
        open_pos = len(self.positions)
        open_orders = sum(
            len(v["buys"]) + len(v["sells"])
            for v in self.open_orders.values()
        )
        unrealized = 0
        return {
            "daily_pnl": round(self.daily_pnl, 2),
            "daily_gross": round(self.daily_gross, 2),
            "daily_fees": round(self.daily_fees, 2),
            "roundtrips": self.total_roundtrips,
            "open_positions": open_pos,
            "open_orders": open_orders,
            "scans": self.scan_count,
        }


# ═══════════════ LEARNING MEMORY ═══════════════
class LearningMemory:
    """Persistent memory across scans and days. Learns from every observation."""

    MEMORY_FILE = PAPER_DIR / "agent_memory.json"

    def __init__(self):
        self.stock_history = {}    # {symbol: {spreads: [], fills: [], patterns: []}}
        self.group_history = {}    # {group: {direction_counts: {}, volume_by_time: {}}}
        self.daily_lessons = []    # [{date, lesson, confidence}]
        self.scan_observations = [] # Current day observations
        self.intraday_snapshots = {} # {symbol: [{time, bid, ask, last, spread, vol}]}
        self.best_performers = {}  # {symbol: {total_pnl, roundtrips, avg_hold, win_rate}}
        self.worst_performers = {} # Same structure
        self.spread_map = {}       # {symbol: {avg_spread, min_spread, max_spread, samples}}
        self.time_patterns = defaultdict(lambda: defaultdict(list))  # {hour: {symbol: [spread]}}
        self._load()

    def _load(self):
        """Load memory from disk."""
        if self.MEMORY_FILE.exists():
            try:
                data = json.loads(self.MEMORY_FILE.read_text(encoding="utf-8"))
                self.stock_history = data.get("stock_history", {})
                self.group_history = data.get("group_history", {})
                self.daily_lessons = data.get("daily_lessons", [])[-100:]  # keep last 100
                self.best_performers = data.get("best_performers", {})
                self.worst_performers = data.get("worst_performers", {})
                self.spread_map = data.get("spread_map", {})
                log.info(f"Memory loaded: {len(self.stock_history)} stocks, {len(self.daily_lessons)} lessons")
            except Exception as e:
                log.warning(f"Memory load failed: {e}")

    def save(self):
        """Save memory to disk."""
        data = {
            "stock_history": self.stock_history,
            "group_history": self.group_history,
            "daily_lessons": self.daily_lessons[-100:],
            "best_performers": self.best_performers,
            "worst_performers": self.worst_performers,
            "spread_map": self.spread_map,
            "last_saved": datetime.now().isoformat(),
        }
        self.MEMORY_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

    def observe_stock(self, symbol, bid, ask, last, volume, ticks, group, et_time):
        """Record a stock observation. Builds up knowledge over time."""
        spread = round(ask - bid, 4) if bid > 0 and ask > 0 else 0
        mid = (ask + bid) / 2 if bid > 0 else last

        # Track intraday snapshots (last 50 per stock)
        if symbol not in self.intraday_snapshots:
            self.intraday_snapshots[symbol] = []
        self.intraday_snapshots[symbol].append({
            "t": et_time[:5],  # HH:MM
            "bid": bid, "ask": ask, "last": last,
            "spread": spread, "vol": volume,
            "ticks": len(ticks) if ticks else 0,
        })
        self.intraday_snapshots[symbol] = self.intraday_snapshots[symbol][-50:]

        # Update spread map
        if symbol not in self.spread_map:
            self.spread_map[symbol] = {"spreads": [], "avg": 0, "min": 999, "max": 0}
        sm = self.spread_map[symbol]
        if spread > 0:
            sm["spreads"].append(spread)
            sm["spreads"] = sm["spreads"][-200:]  # keep last 200 samples
            sm["avg"] = round(sum(sm["spreads"]) / len(sm["spreads"]), 4)
            sm["min"] = min(sm["min"], spread)
            sm["max"] = max(sm["max"], spread)

        # Track buyer/seller from recent ticks
        buyers = sellers = 0
        for t in (ticks or [])[-10:]:
            tp = t.get("price", 0)
            if tp >= mid:
                buyers += 1
            else:
                sellers += 1

        # Update stock history
        if symbol not in self.stock_history:
            self.stock_history[symbol] = {
                "group": group, "observations": 0,
                "buyer_total": 0, "seller_total": 0,
                "last_10_spreads": [],
            }
        sh = self.stock_history[symbol]
        sh["observations"] += 1
        sh["buyer_total"] += buyers
        sh["seller_total"] += sellers
        sh["last_10_spreads"].append(spread)
        sh["last_10_spreads"] = sh["last_10_spreads"][-10:]

        # Update group history
        if group not in self.group_history:
            self.group_history[group] = {"buyer_scans": 0, "seller_scans": 0, "balanced_scans": 0}
        gh = self.group_history[group]
        if buyers > sellers + 2:
            gh["buyer_scans"] += 1
        elif sellers > buyers + 2:
            gh["seller_scans"] += 1
        else:
            gh["balanced_scans"] += 1

        # Time-based spread patterns
        hour = et_time[:2] if et_time else "??"
        self.time_patterns[hour][symbol].append(spread)

    def record_trade_result(self, symbol, pnl, hold_time, strategy):
        """Record a trade outcome for learning."""
        bucket = self.best_performers if pnl > 0 else self.worst_performers
        if symbol not in bucket:
            bucket[symbol] = {"total_pnl": 0, "trades": 0, "wins": 0, "total_hold": 0}
        b = bucket[symbol]
        b["total_pnl"] += pnl
        b["trades"] += 1
        if pnl > 0:
            b["wins"] += 1
        b["total_hold"] += hold_time

    def add_observation(self, text, confidence=50):
        """Add a free-form observation / learning note."""
        self.scan_observations.append({
            "time": datetime.now().isoformat(),
            "text": text,
            "confidence": confidence,
        })

    def end_of_day_summary(self):
        """Generate learning summary for the day."""
        # Aggregate intraday patterns
        wide_spread_stocks = []
        tight_spread_stocks = []
        active_stocks = []

        for sym, sm in self.spread_map.items():
            if sm.get("avg", 0) >= 0.05:
                wide_spread_stocks.append((sym, sm["avg"]))
            elif sm.get("avg", 0) > 0 and sm.get("avg", 0) < 0.02:
                tight_spread_stocks.append((sym, sm["avg"]))

        for sym, snaps in self.intraday_snapshots.items():
            if len(snaps) > 3:
                avg_vol = sum(s["vol"] for s in snaps) / len(snaps)
                if avg_vol > 5000:
                    active_stocks.append((sym, avg_vol))

        wide_spread_stocks.sort(key=lambda x: x[1], reverse=True)
        active_stocks.sort(key=lambda x: x[1], reverse=True)

        # Group direction summary
        group_dirs = []
        for g, gh in self.group_history.items():
            total = gh["buyer_scans"] + gh["seller_scans"] + gh["balanced_scans"]
            if total > 0:
                buyer_pct = gh["buyer_scans"] / total * 100
                direction = "BUYER" if buyer_pct > 55 else ("SELLER" if buyer_pct < 45 else "FLAT")
                group_dirs.append((g, direction, buyer_pct))

        summary = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "observations_today": len(self.scan_observations),
            "stocks_tracked": len(self.intraday_snapshots),
            "wide_spread_mm_candidates": wide_spread_stocks[:15],
            "tight_spread_no_mm": tight_spread_stocks[:10],
            "most_active": active_stocks[:15],
            "group_directions": group_dirs,
            "key_observations": [o["text"] for o in self.scan_observations[-20:]],
        }

        # Save as daily lesson
        lesson = (
            f"Tracked {len(self.intraday_snapshots)} stocks. "
            f"Wide spread MM candidates: {[s[0] for s in wide_spread_stocks[:5]]}. "
            f"Most active: {[s[0] for s in active_stocks[:5]]}. "
            f"Key obs: {len(self.scan_observations)} notes."
        )
        self.daily_lessons.append({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "lesson": lesson,
            "details": summary,
        })

        return summary

    def get_recommendation(self, symbol):
        """Get recommendation for a stock based on accumulated knowledge."""
        sm = self.spread_map.get(symbol, {})
        sh = self.stock_history.get(symbol, {})

        if not sm or not sh:
            return None

        avg_spread = sm.get("avg", 0)
        obs = sh.get("observations", 0)
        buyer_total = sh.get("buyer_total", 0)
        seller_total = sh.get("seller_total", 0)
        total = buyer_total + seller_total

        rec = {
            "symbol": symbol,
            "avg_spread": avg_spread,
            "spread_range": f"${sm.get('min', 0):.3f}-${sm.get('max', 0):.3f}",
            "observations": obs,
            "buyer_pct": round(buyer_total / max(total, 1) * 100, 1),
        }

        # Check if in best/worst performers
        if symbol in self.best_performers:
            bp = self.best_performers[symbol]
            rec["past_pnl"] = bp["total_pnl"]
            rec["past_trades"] = bp["trades"]
            rec["confidence"] = "HIGH" if bp["trades"] >= 3 and bp["total_pnl"] > 0 else "MED"
        elif symbol in self.worst_performers:
            wp = self.worst_performers[symbol]
            rec["past_pnl"] = wp["total_pnl"]
            rec["past_trades"] = wp["trades"]
            rec["confidence"] = "LOW"
        else:
            rec["confidence"] = "NEW"

        return rec

    def get_past_lessons(self, n=5):
        """Get last N daily lessons."""
        return self.daily_lessons[-n:]


# ═══════════════ DATA FETCHER ═══════════════
class MarketDataFetcher:
    """Fetches L1, prints, truth ticks from Hammer."""

    def __init__(self):
        self.hammer = None
        self._connect()

    def _connect(self):
        from app.live.hammer_client import HammerClient, set_hammer_client, get_hammer_client
        self.hammer = get_hammer_client()
        if not self.hammer or not self.hammer.is_connected():
            password = os.getenv("HAMMER_PASSWORD", "")
            host = os.getenv("HAMMER_HOST", "127.0.0.1")
            port = int(os.getenv("HAMMER_PORT", "16400"))
            client = HammerClient(host=host, port=port, password=password)
            if client.connect():
                set_hammer_client(client)
                self.hammer = client
                log.info(f"Hammer connected ({host}:{port})")
            else:
                log.error("Hammer connection failed!")

    def get_l1(self, symbol, timeout=2.0):
        """Get Level 1 data: bid, ask, last, volume."""
        if not self.hammer:
            return None
        try:
            # Use Hammer's getL1 command
            from app.live.hammer_client import SymbolMapper
            hammer_sym = SymbolMapper.to_hammer_symbol(symbol)
            
            result = self.hammer.send_command(
                "getL1",
                {"symbol": hammer_sym},
                timeout=timeout,
            )
            if result and isinstance(result, dict):
                data = result.get("data", result)
                return {
                    "bid": float(data.get("bid", 0) or 0),
                    "ask": float(data.get("ask", 0) or 0),
                    "last": float(data.get("last", 0) or 0),
                    "volume": int(data.get("volume", 0) or 0),
                    "bid_size": int(data.get("bidSize", 0) or 0),
                    "ask_size": int(data.get("askSize", 0) or 0),
                }
        except Exception as e:
            pass
        return None

    def get_recent_ticks(self, symbol, last_n=20, timeout=2.0):
        """Get last N ticks for a symbol."""
        if not self.hammer:
            return []
        try:
            result = self.hammer.get_ticks(
                symbol, lastFew=last_n, tradesOnly=True, timeout=timeout
            )
            if result and "data" in result:
                return result["data"]
        except Exception:
            pass
        return []


# ═══════════════ MM STRATEGY ═══════════════
class MMStrategy:
    """Market Making strategy for preferred stocks."""

    def __init__(self, static_store):
        self.store = static_store
        self.stock_data = {}  # {symbol: {static + dynamic data}}
        self.group_snapshots = defaultdict(list)  # {group: [{time, direction, ...}]}
        self.market_snapshots = []  # [{time, summary}]
        self.observations = []  # Learning notes

    def load_candidates(self):
        """Load MM candidates from saved analysis."""
        analysis = json.load(open(
            r"C:\StockTracker\quant_engine\tt_training_result.json", encoding="utf-8"
        ))
        raw = analysis["raw_analysis"]
        groups = raw.get("groups", {})

        candidates = []
        for g_name, g_data in groups.items():
            for stock in g_data.get("top_stocks", []):
                sym = stock.get("symbol", "")
                static = self.store.get_static_data(sym) or {}

                avg_adv = float(static.get("AVG_ADV", 0) or 0)
                price = float(static.get("prev_close", 0) or 0)
                fbtot = float(static.get("FINAL_THG", 0) or 0)
                sfstot = float(static.get("SHORT_FINAL", 0) or 0)

                if not price: price = 25.0
                if avg_adv < 500: continue  # skip illiquid

                # Calculate lot size (10-15% of ADV, rounded to 100s)
                lot = max(MIN_LOT, min(MAX_LOT, int(avg_adv * LOT_PCT_OF_ADV / 100) * 100))
                # Cap by dollar exposure
                max_lot = int(EXPOSURE_PER_STOCK / price / 100) * 100
                lot = min(lot, max(MIN_LOT, max_lot))

                self.stock_data[sym] = {
                    "symbol": sym,
                    "group": g_name,
                    "price": price,
                    "avg_adv": avg_adv,
                    "fbtot": fbtot,
                    "sfstot": sfstot,
                    "gort": stock.get("gort"),
                    "mm_score": stock.get("mm_score", 0),
                    "interest": stock.get("interest_score", 0),
                    "lot": lot,
                    "exposure": lot * price,
                    "busiest_window": stock.get("busiest_window", ""),
                    "spread_bps": stock.get("overall_spread_bps", 0),
                }
                candidates.append(sym)

        log.info(f"Loaded {len(candidates)} MM candidates")
        return candidates

    def evaluate_opportunity(self, symbol, l1, recent_ticks, portfolio):
        """
        Evaluate MM opportunity for a symbol.
        Returns (action, details) or None.
        """
        if not l1 or l1["bid"] <= 0 or l1["ask"] <= 0:
            return None

        bid = l1["bid"]
        ask = l1["ask"]
        spread = ask - bid
        last = l1["last"] or ((bid + ask) / 2)
        mid = (bid + ask) / 2

        sd = self.stock_data.get(symbol, {})
        if not sd:
            return None

        # Update dynamic data
        sd["live_bid"] = bid
        sd["live_ask"] = ask
        sd["live_last"] = last
        sd["live_spread"] = round(spread, 4)
        sd["live_spread_bps"] = round(spread / mid * 10000, 1) if mid else 0
        sd["live_volume"] = l1.get("volume", 0)

        # ═══ SKIP if already has position or open orders ═══
        if symbol in portfolio.positions:
            return None
        if symbol in portfolio.open_orders:
            buys = portfolio.open_orders[symbol].get("buys", [])
            sells = portfolio.open_orders[symbol].get("sells", [])
            if buys or sells:
                return None  # already have orders, let them work

        # ═══ ENTRY LOGIC: bid + spread*15%, ask - spread*15% ═══
        if spread < 0.02:
            return None  # spread too tight, no MM opportunity

        buy_price = round(bid + spread * SPREAD_ENTRY_PCT, 2)
        sell_price = round(ask - spread * SPREAD_ENTRY_PCT, 2)
        capture = sell_price - buy_price

        lot = sd["lot"]

        # Calculate recent truth tick direction
        buyer_ticks = 0
        seller_ticks = 0
        for t in recent_ticks[-10:]:
            tp = t.get("price", 0)
            if tp >= mid:
                buyer_ticks += 1
            else:
                seller_ticks += 1

        # Strategy decision
        strategy = "S1"  # default spread capture
        confidence = 0
        reason = ""

        if capture >= MIN_CAPTURE:
            # Classic spread capture
            strategy = "S1"
            confidence = min(90, 50 + int(capture / 0.01) * 5)
            reason = f"Spread ${spread:.2f}, capture ${capture:.2f}"
        elif spread >= 0.04:
            # Truth tick frontlama
            strategy = "S2"
            buy_price = round(bid + 0.01, 2)
            sell_price = round(last - 0.01, 2) if last > buy_price + 0.03 else round(ask - 0.01, 2)
            capture = sell_price - buy_price
            if capture >= 0.03:
                confidence = 60
                reason = f"Frontlama last=${last:.2f}, capt=${capture:.2f}"
        
        if confidence == 0 and spread >= 0.03:
            # Range / back-level trading
            strategy = "S4"
            buy_price = round(bid + 0.01, 2)
            sell_price = round(ask - 0.01, 2)
            capture = sell_price - buy_price
            if capture >= 0.02:
                confidence = 40
                reason = f"Back-level spread=${spread:.2f}"

        if confidence == 0:
            return None

        return {
            "action": "place_orders",
            "symbol": symbol,
            "strategy": strategy,
            "buy_price": buy_price,
            "sell_price": sell_price,
            "capture": capture,
            "lot": lot,
            "confidence": confidence,
            "reason": reason,
            "bid": bid,
            "ask": ask,
            "spread": spread,
            "last": last,
            "buyer_ticks": buyer_ticks,
            "seller_ticks": seller_ticks,
        }


# ═══════════════ MAIN LOOP ═══════════════
async def run_paper_trader(dry_run=False, max_scans=0):
    """
    Main paper trading loop.

    Args:
        dry_run: If True, skip market hours check, run limited scans, no Hammer needed.
        max_scans: If > 0, stop after N scans (0 = unlimited, until market close).
    """
    today = datetime.now().strftime("%Y-%m-%d")
    mode = "DRY-RUN" if dry_run else "LIVE"

    log.info("=" * 80)
    log.info(f"QAGENTT PAPER TRADER [{mode}] -- {today}")
    log.info("=" * 80)
    log.info("")

    # ================================================================
    # ADIM 1: STATIC DATA YUKLE
    # ================================================================
    log.info("[1/6] Static data yukleniyor...")
    from app.market_data.static_data_store import initialize_static_store
    store = initialize_static_store()
    store.load_csv()

    # ================================================================
    # ADIM 2: COMPONENTLER HAZIRLA
    # ================================================================
    log.info("[2/6] Componentler hazirlaniyor...")
    strategy = MMStrategy(store)
    portfolio = PaperPortfolio()
    memory = LearningMemory()

    if dry_run:
        fetcher = None
        log.info("  Hammer baglantisi atlanacak (dry-run modu)")
    else:
        fetcher = MarketDataFetcher()

    # ================================================================
    # ADIM 3: GECMIS HAFIZAYI YUKLE
    # ================================================================
    log.info("[3/6] Gecmis hafiza yukleniyor...")
    past_lessons = memory.get_past_lessons(5)
    if past_lessons:
        log.info(f"  {len(past_lessons)} gun gecmis ders bulundu:")
        for lsn in past_lessons[-3:]:
            log.info(f"    [{lsn.get('date', '?')}] {lsn.get('lesson', '')[:120]}")
    else:
        log.info("  Ilk calisma -- henuz hafiza yok, bugun ogrenmeye basliyoruz.")

    # Best/worst performers from memory
    if memory.best_performers:
        top3 = sorted(memory.best_performers.items(), key=lambda x: x[1]["total_pnl"], reverse=True)[:3]
        log.info(f"  Gecmis EN IYI: {[(s, f'${d["total_pnl"]:.0f}') for s, d in top3]}")
    if memory.worst_performers:
        worst3 = sorted(memory.worst_performers.items(), key=lambda x: x[1]["total_pnl"])[:3]
        log.info(f"  Gecmis EN KOTU: {[(s, f'${d["total_pnl"]:.0f}') for s, d in worst3]}")

    # ================================================================
    # ADIM 4: MM ADAYLARI YUKLE VE SIRALA
    # ================================================================
    log.info("[4/6] MM adaylari yukleniyor...")
    candidates = strategy.load_candidates()
    if not candidates:
        log.error("Aday bulunamadi! tt_training_result.json kontrol edin.")
        return

    # Sort by exposure priority: FBtot, ADV, spread potential
    candidates.sort(
        key=lambda s: strategy.stock_data.get(s, {}).get("mm_score", 0),
        reverse=True,
    )

    # Top 30 = active trade, rest = monitoring (learning only)
    active_symbols = candidates[:30]
    monitor_symbols = candidates[30:]

    # ================================================================
    # ADIM 5: BASLANGIC RAPORU
    # ================================================================
    log.info("[5/6] Baslangic raporu:")
    log.info("")
    log.info("  KONFIGURASYON:")
    log.info(f"    Toplam exposure:     ${EXPOSURE_TOTAL:>10,}")
    log.info(f"    Hisse basi max:      ${EXPOSURE_PER_STOCK:>10,}")
    log.info(f"    Lot orani:           ADV'nin %{LOT_PCT_OF_ADV*100:.0f}'i")
    log.info(f"    Min lot:             {MIN_LOT:>10,}")
    log.info(f"    Max lot:             {MAX_LOT:>10,}")
    log.info(f"    Emir sirasi:         BUY  @ bid + spread * {SPREAD_ENTRY_PCT:.0%}")
    log.info(f"                         SELL @ ask - spread * {SPREAD_ENTRY_PCT:.0%}")
    log.info(f"    Min capture:         ${MIN_CAPTURE}/share")
    log.info(f"    Stop loss:           {STOP_LOSS_BPS} bps")
    log.info(f"    Max hold:            {MAX_HOLD_MINUTES} dakika")
    log.info(f"    Scan araligi:        {SCAN_INTERVAL_SEC} saniye ({SCAN_INTERVAL_SEC//60} dk)")
    log.info("")

    log.info(f"  AKTIF TRADE ({len(active_symbols)} hisse):")
    log.info(f"    {'Sym':<13s} {'Fiyat':>6s} {'ADV':>7s} {'Lot':>5s} {'Exp$':>7s} {'FBt':>5s} {'SFt':>5s} {'Grup':<18s}")
    log.info("    " + "-" * 75)
    total_planned_exposure = 0
    for sym in active_symbols:
        sd = strategy.stock_data[sym]
        exp = sd["lot"] * sd["price"]
        total_planned_exposure += exp
        log.info(
            f"    {sym:<13s} ${sd['price']:>5.0f} {sd['avg_adv']:>7,.0f} {sd['lot']:>5d} ${exp:>6,.0f} "
            f"{sd['fbtot']:>5.0f} {sd['sfstot']:>5.0f} {sd['group']:<18s}"
        )
    log.info(f"    {'TOPLAM':<13s} {'':>6s} {'':>7s} {'':>5s} ${total_planned_exposure:>6,.0f}")
    log.info("")

    log.info(f"  MONITORING ({len(monitor_symbols)} hisse): sadece izle + ogren")
    if monitor_symbols:
        log.info(f"    Ornekler: {', '.join(monitor_symbols[:10])}...")
    log.info("")

    # ================================================================
    # ADIM 6: MARKET SAATINI BEKLE veya DRY-RUN BASLA
    # ================================================================
    if dry_run:
        if max_scans <= 0:
            max_scans = 3  # default 3 scans for dry-run
        log.info(f"[6/6] DRY-RUN modu: {max_scans} scan yapilacak (Hammer gerekmiyor)")
        log.info("  Simule verilerle calisacak...")
    else:
        log.info("[6/6] Market saatleri kontrol ediliyor...")
        log.info(f"  Suan: {get_et_time()} ET")
        if not is_market_hours():
            log.info("  Market KAPALI. Acilmasini bekliyorum (9:30 ET / 17:30 TR)...")
            log.info("  (Ctrl+C ile cikabilirsiniz)")
            while not is_market_hours():
                await asyncio.sleep(30)
            log.info("  MARKET ACILDI! Paper trading basliyor...")
        else:
            log.info(f"  Market ACIK! Hemen basliyor...")
    log.info("")

    scan_num = 0
    group_summaries = defaultdict(lambda: {"buyer": 0, "seller": 0, "volume": 0, "symbols": 0, "opportunities": 0})
    all_snapshots = []

    try:
        while (dry_run and scan_num < max_scans) or (not dry_run and is_market_hours()):
            scan_num += 1
            scan_start = time.time()
            portfolio.scan_count = scan_num
            et_time = get_et_time()

            log.info(f"\n--- SCAN #{scan_num} | {et_time} ET ---")

            # Reset group stats for this scan
            for g in group_summaries:
                group_summaries[g] = {"buyer": 0, "seller": 0, "volume": 0, "symbols": 0, "opportunities": 0}

            current_prices = {}
            opportunities = []
            market_state = []

            # ═══ SCAN ALL SYMBOLS (active + monitor) ═══
            # Her 3. scan'de monitor hisseleri de tara (ogrenme)
            scan_monitor = (scan_num % 3 == 0) or dry_run  # dry-run: hep tara
            all_scan_symbols = active_symbols + (monitor_symbols if scan_monitor else [])
            for sym in all_scan_symbols:
                sd = strategy.stock_data.get(sym, {})
                grp = sd.get("group", "unknown")
                is_active = sym in active_symbols

                # Fetch L1 (real or simulated)
                if dry_run:
                    # Simulate with static data + small random spread
                    import random
                    base = sd.get("price", 25.0)
                    spread_sim = round(random.uniform(0.02, 0.12), 2)
                    bid = round(base - spread_sim / 2, 2)
                    ask = round(base + spread_sim / 2, 2)
                    last = round(base + random.uniform(-0.03, 0.03), 2)
                    l1 = {
                        "bid": bid, "ask": ask, "last": last,
                        "volume": int(sd.get("avg_adv", 5000) * random.uniform(0.1, 0.5)),
                        "bid_size": random.randint(1, 20) * 100,
                        "ask_size": random.randint(1, 20) * 100,
                    }
                    # Simulate truth ticks
                    ticks = []
                    for _ in range(random.randint(0, 5)):
                        tp = round(base + random.uniform(-spread_sim, spread_sim), 2)
                        ticks.append({"price": tp, "size": random.randint(1, 10) * 100})
                else:
                    l1 = fetcher.get_l1(sym)
                    if not l1 or l1.get("bid", 0) <= 0:
                        continue
                    ticks = fetcher.get_recent_ticks(sym, last_n=10)

                current_prices[sym] = l1.get("last", 0) or l1.get("bid", 0)

                # ═══ LEARNING: observe everything ═══
                memory.observe_stock(
                    sym, l1["bid"], l1["ask"], l1.get("last", 0),
                    l1.get("volume", 0), ticks, grp, et_time,
                )

                # Check existing order fills (active only)
                if is_active:
                    fills = portfolio.check_fills(sym, ticks, l1["bid"], l1["ask"], l1["last"])
                    for fill in fills:
                        log.info(f"  FILL: {fill[0].upper()} {fill[1]} {fill[3]}@${fill[2]:.2f}")

                # Track group stats
                group_summaries[grp]["symbols"] += 1
                group_summaries[grp]["volume"] += l1.get("volume", 0)
                for t in (ticks or [])[-5:]:
                    tp = t.get("price", 0)
                    mid = (l1["bid"] + l1["ask"]) / 2
                    if tp >= mid:
                        group_summaries[grp]["buyer"] += 1
                    else:
                        group_summaries[grp]["seller"] += 1

                # Spread observation for learning
                spread = round(l1["ask"] - l1["bid"], 4)
                if spread >= 0.06 and not is_active:
                    memory.add_observation(
                        f"Wide spread on {sym} (monitor): ${spread:.3f} "
                        f"bid={l1['bid']:.2f} ask={l1['ask']:.2f} — potential MM",
                        confidence=60,
                    )

                # Evaluate opportunity (active only)
                if is_active:
                    # Get memory recommendation
                    mem_rec = memory.get_recommendation(sym)
                    opp = strategy.evaluate_opportunity(sym, l1, ticks, portfolio)
                    if opp:
                        # Boost confidence if memory says this stock performed well before
                        if mem_rec and mem_rec.get("confidence") == "HIGH":
                            opp["confidence"] = min(95, opp["confidence"] + 15)
                            opp["reason"] += f" [MEM: past winner]"
                        elif mem_rec and mem_rec.get("confidence") == "LOW":
                            opp["confidence"] = max(10, opp["confidence"] - 20)
                            opp["reason"] += f" [MEM: past loser]"
                        opportunities.append(opp)
                        group_summaries[grp]["opportunities"] += 1
                        portfolio.opportunities_seen += 1

                # Record market state
                market_state.append({
                    "sym": sym,
                    "bid": l1["bid"],
                    "ask": l1["ask"],
                    "last": l1.get("last", 0),
                    "spread": spread,
                    "vol": l1.get("volume", 0),
                    "ticks": len(ticks or []),
                    "grp": grp[:12],
                    "active": is_active,
                })

            # ═══ PLACE ORDERS (top opportunities by confidence) ═══
            opportunities.sort(key=lambda x: x["confidence"], reverse=True)

            placed = 0
            total_exposure = sum(
                pos["qty"] * pos["avg_price"]
                for pos in portfolio.positions.values()
            )

            for opp in opportunities:
                if total_exposure >= EXPOSURE_TOTAL:
                    break
                if placed >= 5:  # max 5 new orders per scan
                    break

                sym = opp["symbol"]
                lot = opp["lot"]
                exposure = lot * opp["buy_price"]

                if total_exposure + exposure > EXPOSURE_TOTAL:
                    continue

                # Place both sides
                portfolio.place_order(sym, "buy", opp["buy_price"], lot, "hidden")
                portfolio.place_order(sym, "sell", opp["sell_price"], lot, "hidden")
                placed += 1
                total_exposure += exposure
                portfolio.opportunities_taken += 1

                log.info(
                    f"  ORDER: {sym} {opp['strategy']} "
                    f"BUY {lot}@${opp['buy_price']:.2f} / "
                    f"SELL {lot}@${opp['sell_price']:.2f} "
                    f"(capt=${opp['capture']:.2f}, conf={opp['confidence']}%)"
                )

            # ═══ FORCE CLOSE OLD POSITIONS ═══
            portfolio.force_close_old(current_prices)

            # ═══ SCAN SUMMARY ═══
            elapsed = time.time() - scan_start
            summ = portfolio.summary

            log.info(f"  Scanned: {len(market_state)} symbols in {elapsed:.1f}s")
            log.info(f"  Opportunities: {len(opportunities)} found, {placed} orders placed")
            log.info(
                f"  PnL: ${summ['daily_pnl']:.2f} (gross ${summ['daily_gross']:.2f} - fees ${summ['daily_fees']:.2f})"
            )
            log.info(f"  Roundtrips: {summ['roundtrips']} | Open: {summ['open_positions']} pos, {summ['open_orders']} orders")

            # Group summary
            active_groups = [(g, s) for g, s in group_summaries.items() if s["symbols"] > 0]
            if active_groups and scan_num % 3 == 0:  # every 3rd scan
                log.info("  GROUP STATUS:")
                for g_name, gs in sorted(active_groups, key=lambda x: x[1]["volume"], reverse=True)[:8]:
                    total = gs["buyer"] + gs["seller"]
                    buyer_pct = gs["buyer"] / max(total, 1) * 100
                    direction = "BUY" if buyer_pct > 55 else ("SELL" if buyer_pct < 45 else "FLAT")
                    log.info(
                        f"    {g_name:<20s} {direction:>4s}({buyer_pct:.0f}%) "
                        f"vol={gs['volume']:>8,d} opp={gs['opportunities']}"
                    )

            # Save snapshot
            snapshot = {
                "scan": scan_num,
                "time": datetime.now().isoformat(),
                "et_time": et_time,
                "summary": summ,
                "opportunities": len(opportunities),
                "placed": placed,
                "market_state_count": len(market_state),
            }
            all_snapshots.append(snapshot)

            # Save memory periodically (every 6 scans = ~30 min)
            if scan_num % 6 == 0:
                memory.save()
                log.info(f"  Memory saved ({len(memory.spread_map)} stocks tracked)")

            # Wait for next scan
            wait_time = 5 if dry_run else SCAN_INTERVAL_SEC
            if (dry_run and scan_num >= max_scans) or (not dry_run and not is_market_hours()):
                break
            await asyncio.sleep(wait_time)

    except KeyboardInterrupt:
        log.info("\nKullanici tarafindan durduruldu")

    # ═══ END OF DAY ═══
    log.info("\n" + "=" * 80)
    log.info("MARKET CLOSED — END OF DAY REPORT")
    log.info("=" * 80)

    # Force close all remaining positions
    if portfolio.positions:
        log.info(f"Closing {len(portfolio.positions)} remaining positions...")
        portfolio.force_close_old(current_prices)

    # Cancel remaining orders
    portfolio.cancel_all()

    # Record trade results in memory
    for trade in portfolio.closed_trades:
        memory.record_trade_result(
            trade["symbol"], trade["pnl"], trade["hold_time"], "paper"
        )

    # Generate end-of-day learning summary
    eod_learning = memory.end_of_day_summary()
    memory.save()
    log.info(f"\nEnd-of-day learning saved. Tracked {eod_learning['stocks_tracked']} stocks.")
    if eod_learning.get("wide_spread_mm_candidates"):
        log.info(f"  Wide spread candidates: {eod_learning['wide_spread_mm_candidates'][:8]}")
    if eod_learning.get("most_active"):
        log.info(f"  Most active today: {eod_learning['most_active'][:8]}")

    # Final summary
    summ = portfolio.summary
    log.info(f"\nDAILY PNL: ${summ['daily_pnl']:.2f}")
    log.info(f"  Gross: ${summ['daily_gross']:.2f}")
    log.info(f"  Fees: ${summ['daily_fees']:.2f}")
    log.info(f"  Roundtrips: {summ['roundtrips']}")
    log.info(f"  Scans: {summ['scans']}")
    log.info(f"  Opportunities: {portfolio.opportunities_seen} seen, {portfolio.opportunities_taken} taken")

    # Save daily results
    daily_result = {
        "date": today,
        "summary": summ,
        "fills": portfolio.fills,
        "closed_trades": portfolio.closed_trades,
        "snapshots": all_snapshots,
        "observations": strategy.observations,
        "config": {
            "exposure_total": EXPOSURE_TOTAL,
            "exposure_per_stock": EXPOSURE_PER_STOCK,
            "lot_pct_adv": LOT_PCT_OF_ADV,
            "min_capture": MIN_CAPTURE,
            "spread_entry_pct": SPREAD_ENTRY_PCT,
            "scan_interval": SCAN_INTERVAL_SEC,
            "active_symbols": len(active_symbols),
            "monitor_symbols": len(monitor_symbols),
        },
    }

    result_file = PAPER_DIR / f"{today}.json"
    result_file.write_text(
        json.dumps(daily_result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    log.info(f"\nResults saved: {result_file}")

    # Print trade log
    if portfolio.closed_trades:
        log.info("\nTRADE LOG:")
        log.info(f"{'Symbol':<12s} {'Entry':>7s} {'Exit':>7s} {'Qty':>5s} {'PnL':>8s} {'Hold':>5s}")
        log.info("-" * 50)
        for t in portfolio.closed_trades:
            log.info(
                f"  {t['symbol']:<10s} ${t['entry_price']:>5.2f} ${t['exit_price']:>5.2f} "
                f"{t['qty']:>5d} ${t['pnl']:>7.2f} {t['hold_time']:>4d}m"
            )

    # ═══ SEND TO CLAUDE FOR ANALYSIS ═══
    if portfolio.closed_trades or portfolio.fills:
        log.info("\nSending to Claude for end-of-day analysis...")
        try:
            from app.agent.claude_client import ClaudeClient
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if api_key:
                client = ClaudeClient(api_key)
                eod_prompt = f"""
## PAPER TRADING GUNLUK RAPOR — {today}

Bugun {summ['scans']} scan yapildi, {portfolio.opportunities_seen} firsat goruldu, {portfolio.opportunities_taken} emir verildi.

SONUC:
- Gunluk PnL: ${summ['daily_pnl']:.2f}
- Gross: ${summ['daily_gross']:.2f}, Fees: ${summ['daily_fees']:.2f}
- Roundtrip: {summ['roundtrips']}

KAPANAN ISLEMLER:
{json.dumps(portfolio.closed_trades[:20], indent=2, default=str)}

GOZLEMLER:
- Hangi stratejiler ise yaradi?
- Nereler kolaydi, nereler zordu?
- Yarin icin ne onerirsin?
- Bu PnL surdurulebilir mi?
- Hangi hisselerde daha agresif olunmali?
- Risk/return analizi yap.
"""
                response = client._sync_call(
                    prompt=eod_prompt,
                    system_prompt="Sen MM paper trading analisti. Turkce yaz. Gercekci degerlendirme yap.",
                    temperature=0.3,
                    max_tokens=2048,
                )
                if response and "ERROR" not in response:
                    eod_file = PAPER_DIR / f"{today}_claude.txt"
                    eod_file.write_text(response, encoding="utf-8")
                    log.info(f"Claude analysis saved: {eod_file}")
                    log.info(f"\nCLAUDE EOD ANALYSIS:\n{response[:1000]}")
        except Exception as e:
            log.error(f"Claude error: {e}")

    log.info("\n" + "=" * 80)
    log.info("PAPER TRADER SESSION COMPLETE")
    log.info("=" * 80)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="QAGENTT Paper Trading Agent")
    parser.add_argument("--dry-run", action="store_true",
                        help="Test modu: market saati disinda, simule veriyle calisir")
    parser.add_argument("--scans", type=int, default=0,
                        help="Max scan sayisi (0 = market kapanana kadar)")
    args = parser.parse_args()

    asyncio.run(run_paper_trader(dry_run=args.dry_run, max_scans=args.scans))
