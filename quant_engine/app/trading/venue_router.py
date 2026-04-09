"""
Venue-Based Order Router

Analyzes last 5 truth ticks' venues and routes orders to the venue
with the most prints. Orders >= 400 lots are split into 200-lot chunks
for better fill rates.

Logic:
  < 400 lot → single order, SMART routing
  >= 400 lot → split into 200-lot chunks:
      - ~Half of chunks: route to dominant venue
      - ~Other half: SMART routing
      - Each 200-lot chunk is a separate order
      - FNRA → IBKR: DARK, Hammer: SMART (no dark pool direct)
"""

from __future__ import annotations
import json
import math
import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from collections import Counter
from loguru import logger


# ═══════════════════════════════════════════════════════════════
# VENUE MAPPING: Truth Tick Venue → Broker Routing Code
# ═══════════════════════════════════════════════════════════════

# Truth tick venue codes → Hammer Pro Routing field
TRUTH_TICK_TO_HAMMER: Dict[str, str] = {
    "FNRA":  "IEX",     # FINRA/OTC dark → route to IEX (no dark pool in Hammer)
    "NSDQ":  "NSDQ",    # Nasdaq
    "NYSE":  "NYSE",    # New York Stock Exchange
    "ARCA":  "ARCA",    # NYSE Arca
    "EDGX":  "EDGX",    # Cboe EDGX
    "BATS":  "BATS",    # Cboe BZX
    "BZX":   "BATS",    # Alias
    "BYX":   "BYX",     # Cboe BYX
    "IEX":   "IEX",     # Investors Exchange
    "IEXG":  "IEX",     # Alias
    "EDGA":  "EDGA",    # Cboe EDGA
    "MEMX":  "MEMX",    # MEMX
    "PSX":   "PSX",     # Nasdaq PSX
    "AMEX":  "AMEX",    # NYSE American
    "PHLX":  "PHLX",    # Nasdaq PHLX
}

# Truth tick venue codes → IBKR contract.exchange
# ALL venues map to SMART to avoid IB Gateway direct routing restrictions:
# - Error 10311: "Direct routed orders may result in higher trade fees" (ISLAND, ARCA)
# - Error 200: "Invalid exchange" (DARK — not available for all symbols)
# Venue analysis is still used for Hammer routing (no such restriction).
TRUTH_TICK_TO_IBKR: Dict[str, str] = {
    "FNRA":  "SMART",   # FINRA/OTC dark → SMART (DARK exchange causes Error 200)
    "NSDQ":  "SMART",   # Nasdaq → SMART (ISLAND causes Error 10311)
    "NYSE":  "SMART",   # New York Stock Exchange
    "ARCA":  "SMART",   # NYSE Arca → SMART (direct ARCA causes Error 10311)
    "EDGX":  "SMART",   # Cboe EDGX
    "BATS":  "SMART",   # Cboe BZX
    "BZX":   "SMART",   # Alias
    "BYX":   "SMART",   # Cboe BYX
    "IEX":   "SMART",   # Investors Exchange
    "IEXG":  "SMART",   # Alias
    "EDGA":  "SMART",   # Cboe EDGA
    "MEMX":  "SMART",   # MEMX
    "PSX":   "SMART",   # Nasdaq PSX
    "AMEX":  "SMART",   # NYSE American
    "PHLX":  "SMART",   # Nasdaq PHLX
}

# Chunk size for lot splitting
LOT_CHUNK_SIZE = 200

# Minimum lot count for venue-based splitting
MIN_QTY_FOR_SPLIT = 400


@dataclass
class OrderChunk:
    """A single chunk of a split order with venue routing."""
    qty: int
    routing_hammer: str   # Hammer Pro Routing value ("", "NSDQ", "ARCA", etc.)
    routing_ibkr: str     # IBKR contract.exchange value ("SMART", "ISLAND", "DARK", etc.)
    chunk_index: int      # 0-based index
    is_smart: bool        # True if this chunk uses SMART/default routing


@dataclass
class VenueAnalysis:
    """Result of truth tick venue analysis."""
    dominant_venue: str           # Most common venue in truth ticks (e.g., "FNRA")
    venue_counts: Dict[str, int]  # Venue → print count
    total_ticks: int              # Total truth ticks analyzed
    dominant_pct: float           # Percentage of dominant venue (0-100)
    ticks_age_seconds: float      # Age of newest tick in seconds


class VenueRouter:
    """
    Analyzes truth tick venues and produces venue-routed order chunks.
    
    Splitting Rules:
      < 400 lot → single SMART order (no splitting)
      >= 400 lot → split into 200-lot chunks:
        - ~Half of total → dominant venue (each as separate 200 order)
        - ~Other half → SMART routing (each as separate 200 order)
        - FNRA: IBKR→DARK, Hammer→SMART
    
    Usage:
        router = VenueRouter(redis_client)
        chunks = router.route_order("PSA PRG", total_qty=800)
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self._init_redis()
        # Cache of Hammer Pro's available routing options (fetched at runtime)
        self._hammer_routes: Optional[List[str]] = None

    def _init_redis(self):
        if self._redis:
            return
        try:
            from app.core.redis_client import get_redis_client
            self._redis = get_redis_client()
        except Exception:
            pass

    # ─── PUBLIC API ─────────────────────────────────────────────

    def analyze_venue(self, symbol: str, tick_count: int = 5) -> VenueAnalysis:
        """
        Analyze last N truth ticks for a symbol and determine dominant venue.
        
        Returns VenueAnalysis with dominant venue, counts, and freshness.
        """
        ticks = self._fetch_truth_ticks(symbol, tick_count)

        if not ticks:
            return VenueAnalysis(
                dominant_venue="",
                venue_counts={},
                total_ticks=0,
                dominant_pct=0.0,
                ticks_age_seconds=999999,
            )

        # Count venues
        venues = []
        for tick in ticks:
            venue = (tick.get("venue") or tick.get("exch") or "").upper().strip()
            if venue:
                venues.append(venue)

        if not venues:
            return VenueAnalysis(
                dominant_venue="",
                venue_counts={},
                total_ticks=len(ticks),
                dominant_pct=0.0,
                ticks_age_seconds=self._tick_age(ticks),
            )

        counter = Counter(venues)
        dominant_venue, dominant_count = counter.most_common(1)[0]
        dominant_pct = (dominant_count / len(venues)) * 100

        return VenueAnalysis(
            dominant_venue=dominant_venue,
            venue_counts=dict(counter),
            total_ticks=len(ticks),
            dominant_pct=dominant_pct,
            ticks_age_seconds=self._tick_age(ticks),
        )

    def route_order(
        self,
        symbol: str,
        total_qty: int,
        tick_count: int = 5,
    ) -> List[OrderChunk]:
        """
        Route an order based on truth tick venue analysis.
        
        < 400 lot → single SMART order
        >= 400 lot → 200-lot chunks, ~half venue-routed, ~half SMART
        
        Returns list of OrderChunk objects ready for execution.
        """
        total_qty = int(total_qty)

        if total_qty < MIN_QTY_FOR_SPLIT:
            # Single SMART order — no splitting needed
            return [OrderChunk(
                qty=total_qty,
                routing_hammer="",
                routing_ibkr="SMART",
                chunk_index=0,
                is_smart=True,
            )]

        # ─── Analyze dominant venue ───
        analysis = self.analyze_venue(symbol, tick_count)

        # Determine venue routing codes
        has_venue = bool(analysis.dominant_venue and analysis.dominant_pct >= 40)
        if has_venue:
            venue = analysis.dominant_venue
            hammer_route = TRUTH_TICK_TO_HAMMER.get(venue, "")
            ibkr_route = TRUTH_TICK_TO_IBKR.get(venue, "SMART")

            # Validate Hammer route is available (if we've fetched settings)
            if self._hammer_routes is not None and hammer_route:
                if hammer_route not in self._hammer_routes:
                    logger.debug(
                        f"[VenueRouter] {symbol}: Hammer route '{hammer_route}' not available, "
                        f"falling back to SMART. Available: {self._hammer_routes}"
                    )
                    hammer_route = ""
        else:
            venue = ""
            hammer_route = ""
            ibkr_route = "SMART"

        # ─── Split into 200-lot chunks ───
        total_chunks = math.ceil(total_qty / LOT_CHUNK_SIZE)
        
        # ~Half go to dominant venue, ~half go SMART
        venue_chunk_count = total_chunks // 2  # floor division → at least half stays SMART
        if venue_chunk_count < 1 and has_venue:
            venue_chunk_count = 1  # At least 1 venue chunk if we have a signal
        
        smart_chunk_count = total_chunks - venue_chunk_count
        
        # If no venue signal, all SMART
        if not has_venue:
            venue_chunk_count = 0
            smart_chunk_count = total_chunks

        # Build chunks: venue chunks first, then SMART chunks
        chunks: List[OrderChunk] = []
        remaining = total_qty
        chunk_idx = 0

        # Venue-routed chunks (first half)
        for i in range(venue_chunk_count):
            chunk_qty = min(LOT_CHUNK_SIZE, remaining)
            if chunk_qty <= 0:
                break
            chunks.append(OrderChunk(
                qty=chunk_qty,
                routing_hammer=hammer_route,
                routing_ibkr=ibkr_route,
                chunk_index=chunk_idx,
                is_smart=(hammer_route == "" and ibkr_route == "SMART"),
            ))
            remaining -= chunk_qty
            chunk_idx += 1

        # SMART chunks (second half)
        while remaining > 0:
            chunk_qty = min(LOT_CHUNK_SIZE, remaining)
            chunks.append(OrderChunk(
                qty=chunk_qty,
                routing_hammer="",
                routing_ibkr="SMART",
                chunk_index=chunk_idx,
                is_smart=True,
            ))
            remaining -= chunk_qty
            chunk_idx += 1

        # Log
        if has_venue:
            logger.info(
                f"[VenueRouter] {symbol}: {total_qty} lot → {len(chunks)} chunks | "
                f"Venue={venue} ({analysis.dominant_pct:.0f}%) "
                f"→ {venue_chunk_count}×{venue} + {smart_chunk_count}×SMART | "
                f"Hammer='{hammer_route}' IBKR='{ibkr_route}' | "
                f"Venues={analysis.venue_counts}"
            )
        else:
            logger.info(
                f"[VenueRouter] {symbol}: {total_qty} lot → {len(chunks)} chunks | "
                f"No dominant venue (>40%) → all SMART | "
                f"Venues={analysis.venue_counts}"
            )

        return chunks

    def set_hammer_routes(self, routes: List[str]):
        """Set available Hammer Pro routing options (from tradingAccountSettings)."""
        self._hammer_routes = [r.upper() for r in routes] if routes else None
        logger.info(f"[VenueRouter] Hammer routing options set: {self._hammer_routes}")

    # ─── INTERNAL ───────────────────────────────────────────────

    def _fetch_truth_ticks(self, symbol: str, count: int = 5) -> list:
        """Fetch last N truth ticks from Redis."""
        try:
            if not self._redis:
                return []
            redis_sync = getattr(self._redis, "sync", self._redis)

            # Primary: tt:ticks:{symbol}
            data = redis_sync.get(f"tt:ticks:{symbol}")
            if data:
                raw = data.decode() if isinstance(data, bytes) else data
                ticks = json.loads(raw)
                if ticks and isinstance(ticks, list):
                    now = time.time()
                    valid = []
                    for tick in reversed(ticks):  # newest first
                        ts = tick.get("ts", 0)
                        if ts > 0 and (now - ts) > 86400:
                            continue
                        price = float(tick.get("price", 0))
                        size = float(tick.get("size", 0))
                        venue = str(tick.get("exch", tick.get("venue", "")))
                        if price > 0 and size > 0:
                            valid.append({
                                "price": price,
                                "venue": venue,
                                "size": size,
                                "ts": ts,
                            })
                        if len(valid) >= count:
                            break
                    if valid:
                        return valid

            # Fallback: truthtick:latest:{symbol}
            legacy = redis_sync.get(f"truthtick:latest:{symbol}")
            if legacy:
                raw = legacy.decode() if isinstance(legacy, bytes) else legacy
                tick = json.loads(raw)
                price = float(tick.get("price", 0))
                size = float(tick.get("size", 0))
                venue = str(tick.get("venue", tick.get("exch", "")))
                if price > 0 and size > 0:
                    return [{"price": price, "venue": venue, "size": size, "ts": 0}]

            return []
        except Exception as e:
            logger.debug(f"[VenueRouter] Truth ticks fetch for {symbol}: {e}")
            return []

    def _tick_age(self, ticks: list) -> float:
        """Get age of newest tick in seconds."""
        if not ticks:
            return 999999
        newest_ts = max(t.get("ts", 0) for t in ticks)
        if newest_ts <= 0:
            return 999999
        return time.time() - newest_ts


# ─── SINGLETON ──────────────────────────────────────────────────

_venue_router: Optional[VenueRouter] = None


def get_venue_router() -> VenueRouter:
    """Get or create singleton VenueRouter."""
    global _venue_router
    if _venue_router is None:
        _venue_router = VenueRouter()
    return _venue_router
