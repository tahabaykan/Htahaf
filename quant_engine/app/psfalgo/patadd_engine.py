"""
PATADD Engine — Pattern-Based Position Increase Engine v2.0
===========================================================

Uses Pattern Suggestions (ex-div cycle analysis) to open LONG/SHORT positions
when a stock's "buy day" or "short day" arrives.

DIFFERENCES FROM ADDNEWPOS:
  - Source:   Pattern Suggestions (BUY_NOW/SHORT_NOW) instead of tumcsvlong/short
  - Scoring:  LPAT = PatternScore × Fbtot | SPAT = PatternScore / SFStot
  - Selection: Ranked purely by LPAT/SPAT score (NO DOSGRUP weight allocation)

SAME AS ADDNEWPOS v3.0:
  - Filters:  Fbtot > 1.10 (long), SFStot < 1.10 (short = grupta pahalı = iyi)
  - Lot sizing: Portfolio rules (MAXALW × multiplier) — pure, no score scaling
  - Guards:   MAXALW remaining, MinMax validation (XNL engine'de)
  - Existing position checks, min_holding_days

v2.0 CHANGES:
  - score_mult LOT SCALING KALDIRILDI (skor sadece sıralama için, lot'a karışmaz)
  - Lot hesabı sade MAXALW × portfolio rule (JanallApp birebir)
  - calculate_rounded_lot kullanılıyor (ADDNEWPOS tutarlılık)

Priority: 17 (between KARBOTU=20 and ADDNEWPOS=15)
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import math

from app.core.logger import logger
from app.psfalgo.decision_models import (
    DecisionRequest,
    DecisionResponse,
    Decision,
    PositionSnapshot,
    SymbolMetrics,
    ExposureSnapshot,
    RejectReason,
)
from app.psfalgo.intent_math import calculate_rounded_lot, compute_intents


# ────────────────────────────────────────────────────────────────────
# Data Models
# ────────────────────────────────────────────────────────────────────

@dataclass
class PataddCandidate:
    """A scored candidate from pattern suggestions."""
    symbol: str
    direction: str              # 'LONG' or 'SHORT'
    pat_score: float            # LPAT or SPAT composite score
    pattern_score: float        # Raw pattern suggestion score
    qe_factor: float            # Fbtot (LONG) or SFStot (SHORT)

    # Pattern info
    win_rate: float = 0.0
    sharpe: float = 0.0
    confidence_pct: float = 0.0
    strategy: str = ""
    entry_date: str = ""
    exit_date: str = ""
    exdiv_date: str = ""
    holding_days: int = 0
    expected_return: float = 0.0

    # QE metrics (enriched)
    fbtot: float = 0.0
    sfstot: float = 0.0
    gort: float = 0.0
    sma63_chg: float = 0.0
    bid_buy_ucuzluk: float = 0.0
    ask_sell_pahalilik: float = 0.0

    # Lot calculation
    maxalw: int = 0
    avg_adv: float = 0.0
    current_position: int = 0
    calculated_lot: int = 0
    final_lot: int = 0
    order_price: Optional[float] = None

    # L1
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    spread: float = 0.0
    final_thg: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {k: (round(v, 4) if isinstance(v, float) else v)
                for k, v in self.__dict__.items()}


@dataclass
class PataddResult:
    """Result of a PATADD engine run."""
    lpat_orders: List[Decision] = field(default_factory=list)
    spat_orders: List[Decision] = field(default_factory=list)
    lpat_filtered: List[Decision] = field(default_factory=list)
    spat_filtered: List[Decision] = field(default_factory=list)
    execution_time_ms: float = 0.0
    errors: List[str] = field(default_factory=list)

    @property
    def total_orders(self) -> int:
        return len(self.lpat_orders) + len(self.spat_orders)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'lpat_orders': len(self.lpat_orders),
            'spat_orders': len(self.spat_orders),
            'lpat_filtered': len(self.lpat_filtered),
            'spat_filtered': len(self.spat_filtered),
            'total_orders': self.total_orders,
            'execution_time_ms': round(self.execution_time_ms, 2),
            'errors': self.errors,
        }


# ────────────────────────────────────────────────────────────────────
# Portfolio Rules (same as ADDNEWPOS — Janall-compatible)
# ────────────────────────────────────────────────────────────────────

DEFAULT_PORTFOLIO_RULES = [
    {'max_portfolio_percent': 1.0, 'maxalw_multiplier': 0.50},
    {'max_portfolio_percent': 3.0, 'maxalw_multiplier': 0.40},
    {'max_portfolio_percent': 5.0, 'maxalw_multiplier': 0.30},
    {'max_portfolio_percent': 7.0, 'maxalw_multiplier': 0.20},
    {'max_portfolio_percent': 10.0, 'maxalw_multiplier': 0.10},
    {'max_portfolio_percent': 100.0, 'maxalw_multiplier': 0.05},
]


# ────────────────────────────────────────────────────────────────────
# Engine
# ────────────────────────────────────────────────────────────────────

class PataddEngine:
    """
    PATADD Engine — Pattern-based position increase.

    Pipeline (mirrors ADDNEWPOS):
      1. Fetch pattern signals (BUY_NOW / SHORT_NOW)
      2. For each signal, enrich with QE metrics
      3. Apply ADDNEWPOS-identical filters (Fbtot < 1.0*, SFStot < 1.10*, etc.)
      4. Calculate LPAT/SPAT composite score = PatternScore × Fbtot/SFStot
      5. Rank by LPAT/SPAT score (instead of DOSGRUP diversification)
      6. Calculate lot (ADDNEWPOS Portfolio Rules — MAXALW × multiplier)
      7. Guards: MAXALW remaining, company limit, existing position
    """

    LOT_ROUNDING = 100
    MIN_LOT = 200

    def __init__(self):
        self._settings: Dict[str, Any] = {}
        self._portfolio_rules = list(DEFAULT_PORTFOLIO_RULES)
        
        # Exposure-based intent gating (ADDNEWPOS benzeri ama daha toleranslı)
        # ADDNEWPOS: hard=92%, PATADD: hard=95% (pattern güvenince daha rahat)
        self.intent_model_config = {
            'hard_threshold_pct': 95.0,   # Hard cutoff at 95% exposure
            'soft_ratio_num': 12,         # S = 95 * 12/13 ≈ 87.7%
            'soft_ratio_den': 13,
            'Amax': 100.0,               # Full intent at low exposure
            'Asoft': 20.0,               # Cautious intent at soft boundary
            'pn': 1.25,                  # Normal zone decay exponent
            'q': 2.14,                   # Normal zone steepness
            'ps': 1.50,                  # Soft zone decay exponent
        }
        
        logger.info("[PATADD] Engine initialized")

    # ── public entry point ────────────────────────────────────────

    async def run(
        self,
        request: DecisionRequest,
        account_id: str,
        settings: Optional[Dict[str, Any]] = None,
    ) -> PataddResult:
        """
        Main entry — called by XNL during Phase 2.5.

        Returns PataddResult with Decision objects (same type as ADDNEWPOS).
        """
        start = datetime.now()
        self._settings = settings or {}
        result = PataddResult()

        try:
            # ── 0. EXPOSURE GATING (ADDNEWPOS benzeri) ──────────
            exposure_pct = 0.0
            pick_count = 20  # Default: max 20 per side
            if request and request.exposure and request.exposure.pot_max and request.exposure.pot_max > 0:
                exposure_pct = (request.exposure.pot_total / request.exposure.pot_max) * 100.0
                add_intent, _, regime = compute_intents(exposure_pct, self.intent_model_config)
                
                # PickCount: Intent'e göre kaç sinyal seçeceğiz
                if regime == 'HARD' or add_intent < 0.1:
                    pick_count = 0
                elif add_intent > 45:
                    pick_count = 20
                elif add_intent > 25:
                    pick_count = 15
                elif add_intent > 10:
                    pick_count = 10
                else:
                    pick_count = 5  # Çok düşük intent'te bile 5 pattern dene
                
                logger.info(
                    f"[PATADD] Exposure gating: pot={request.exposure.pot_total:.0f}/{request.exposure.pot_max:.0f} "
                    f"({exposure_pct:.1f}%) | Intent={add_intent:.0f} Regime={regime} PickCount={pick_count}"
                )
                
                if pick_count == 0:
                    logger.info(f"[PATADD] ⛔ Exposure too high — SKIPPING (Regime={regime}, Intent={add_intent:.1f})")
                    elapsed = (datetime.now() - start).total_seconds() * 1000
                    result.execution_time_ms = elapsed
                    return result
            else:
                logger.info("[PATADD] Exposure data not available — running without gating")

            # ── 1. Fetch active pattern signals ─────────────────
            active_signals = await self._fetch_active_signals()
            if not active_signals:
                logger.info("[PATADD] No active pattern signals (BUY_NOW/SHORT_NOW)")
                return result

            longs = [s for s in active_signals if s.get('signal') == 'BUY_NOW']
            shorts = [s for s in active_signals if s.get('signal') == 'SHORT_NOW']
            logger.info(
                f"[PATADD] Active signals: {len(longs)} LONG (BUY_NOW), "
                f"{len(shorts)} SHORT (SHORT_NOW)"
            )

            # Build position map from request
            existing_map: Dict[str, float] = {}
            if request and hasattr(request, 'positions') and request.positions:
                for pos in request.positions:
                    pot = getattr(pos, 'potential_qty', pos.qty)
                    if pot is None:
                        pot = pos.qty
                    existing_map[pos.symbol] = pot

            # ── 1b. Janall cache enrichment (same as ADDNEWPOS/RUNALL) ──
            # Refresh fbtot/sfstot/gort/ucuzluk/pahalilik from live Janall cache
            try:
                from app.api.market_data_routes import get_janall_metrics_engine as _get_janall
                _janall = _get_janall()
                if _janall and hasattr(_janall, 'symbol_metrics_cache') and request and request.metrics:
                    _enriched = 0
                    for _sym, _sm in request.metrics.items():
                        _jd = _janall.symbol_metrics_cache.get(_sym, {})
                        if _jd:
                            _sm.fbtot = _jd.get('fbtot')
                            _sm.sfstot = _jd.get('sfstot')
                            _sm.gort = _jd.get('gort')
                            _sm.sma63_chg = _jd.get('sma63_chg')
                            _sm.sma246_chg = _jd.get('sma246_chg')
                            _sm.bench_chg = _jd.get('bench_chg')
                            _sm.ask_sell_pahalilik = _jd.get('ask_sell_pahalilik')
                            _sm.bid_buy_ucuzluk = _jd.get('bid_buy_ucuzluk')
                            _enriched += 1
                    
                    # Create metrics for signal symbols NOT in request.metrics
                    _created = 0
                    from app.market_data.static_data_store import get_static_store
                    _static = get_static_store()
                    for sig in active_signals:
                        _sym = sig.get('ticker', '').strip().upper()
                        if _sym in request.metrics or not _sym:
                            continue
                        _jd = _janall.symbol_metrics_cache.get(_sym, {})
                        if not _jd:
                            continue
                        _bd = _jd.get('_breakdown', {})
                        _inp = _bd.get('inputs', {})
                        _sd = _static.get_static_data(_sym) if _static else None
                        request.metrics[_sym] = SymbolMetrics(
                            symbol=_sym,
                            timestamp=datetime.now(),
                            bid=_inp.get('bid'),
                            ask=_inp.get('ask'),
                            last=_inp.get('last'),
                            prev_close=_inp.get('prev_close'),
                            spread=_jd.get('spread'),
                            fbtot=_jd.get('fbtot'),
                            sfstot=_jd.get('sfstot'),
                            gort=_jd.get('gort'),
                            sma63_chg=_jd.get('sma63_chg'),
                            sma246_chg=_jd.get('sma246_chg'),
                            bench_chg=_jd.get('bench_chg'),
                            bid_buy_ucuzluk=_jd.get('bid_buy_ucuzluk'),
                            ask_sell_pahalilik=_jd.get('ask_sell_pahalilik'),
                            final_thg=float(_sd.get('FINAL_THG', 0) or 0) if _sd else None,
                            short_final=float(_sd.get('SHORT_FINAL', 0) or 0) if _sd else None,
                            avg_adv=float(_sd.get('AVG_ADV', 0) or 0) if _sd else None,
                        )
                        _created += 1
                    
                    if _enriched > 0 or _created > 0:
                        logger.info(
                            f"[PATADD] 🔄 Janall cache refresh: enriched={_enriched}, "
                            f"created={_created} new metrics"
                        )
            except Exception as e:
                logger.warning(f"[PATADD] ⚠️ Janall cache enrichment failed: {e}")

            # ── 2. Process LPAT (long) — PickCount ile sınırla ──
            lpat_decisions, lpat_filtered = await self._process_side(
                signals=longs[:pick_count] if pick_count < len(longs) else longs,
                direction='LONG',
                request=request,
                existing_map=existing_map,
            )
            result.lpat_orders = lpat_decisions
            result.lpat_filtered = lpat_filtered

            # ── 3. Process SPAT (short) — PickCount ile sınırla ──
            spat_decisions, spat_filtered = await self._process_side(
                signals=shorts[:pick_count] if pick_count < len(shorts) else shorts,
                direction='SHORT',
                request=request,
                existing_map=existing_map,
            )
            result.spat_orders = spat_decisions
            result.spat_filtered = spat_filtered

        except Exception as exc:
            logger.error(f"[PATADD] Engine error: {exc}", exc_info=True)
            result.errors.append(str(exc))

        elapsed = (datetime.now() - start).total_seconds() * 1000
        result.execution_time_ms = elapsed

        total_long_lots = sum(d.calculated_lot or 0 for d in result.lpat_orders)
        total_short_lots = sum(d.calculated_lot or 0 for d in result.spat_orders)
        logger.info(
            f"[PATADD] ✅ Run done in {elapsed:.1f}ms — "
            f"LPAT={len(result.lpat_orders)} ({total_long_lots} lots), "
            f"SPAT={len(result.spat_orders)} ({total_short_lots} lots)"
        )
        return result

    # ── fetch pattern suggestions ─────────────────────────────────

    async def _fetch_active_signals(self) -> List[Dict[str, Any]]:
        """
        Call the Pattern Suggestions builder directly (in-process).
        Returns list of dicts with signal='BUY_NOW' or 'SHORT_NOW'.
        """
        try:
            from app.api.pattern_suggestions_routes import (
                _build_suggestions, _enrich_with_qe_data,
            )
            import pandas as pd
            from datetime import timedelta

            today = pd.Timestamp(datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0))
            if today.weekday() >= 5:
                today += timedelta(days=(7 - today.weekday()))

            data, err = _build_suggestions(today)
            if err or data is None:
                logger.warning(f"[PATADD] _build_suggestions error: {err}")
                return []

            active = data.get('active_longs', []) + data.get('active_shorts', [])
            active = _enrich_with_qe_data(active)

            # Respect excluded tickers
            from app.api.pattern_suggestions_routes import _load_excluded
            excluded_keys = _load_excluded()
            included = []
            for t in active:
                key = f"{t['ticker']}_{t['direction']}_{t['entry_date']}"
                if key not in excluded_keys:
                    included.append(t)

            return included

        except Exception as exc:
            logger.error(f"[PATADD] Failed to fetch signals: {exc}", exc_info=True)
            return []

    # ── process one side ──────────────────────────────────────────

    async def _process_side(
        self,
        signals: List[Dict[str, Any]],
        direction: str,
        request: DecisionRequest,
        existing_map: Dict[str, float],
    ) -> Tuple[List[Decision], List[Decision]]:
        """
        Process all signals for one direction.
        Uses same filter logic as ADDNEWPOS.
        Returns (decisions, filtered_out) where both are Decision objects.
        """
        if not signals:
            return [], []

        label = 'LPAT' if direction == 'LONG' else 'SPAT'
        max_orders = int(self._settings.get('max_orders_per_side', 10))

        # PATADD thresholds (daha toleranslı — pattern güvenince giriş daha rahat)
        fbtot_gt = float(self._settings.get('fbtot_gt', 0.90))
        # SFStot: düşük SFStot = pahalı = iyi short (2.00'ye kadar kabul)
        sfstot_lt = float(self._settings.get('sfstot_lt', 2.00))
        # Intraday pricing thresholds (PATADD toleranslı: +5¢/-5¢)
        bid_buy_ucuzluk_lt = float(self._settings.get('bid_buy_ucuzluk_lt', 0.05))
        ask_sell_pahalilik_gt = float(self._settings.get('ask_sell_pahalilik_gt', -0.05))
        max_lot_per_symbol = int(self._settings.get('max_lot_per_symbol', 2000))
        min_lot = int(self._settings.get('min_lot', self.MIN_LOT))
        min_holding_days = int(self._settings.get('min_holding_days', 3))

        # LPAT/SPAT composite score thresholds
        lpat_threshold = float(self._settings.get('lpat_threshold', 45.0))
        spat_threshold = float(self._settings.get('spat_threshold', 30.0))
        score_threshold = lpat_threshold if direction == 'LONG' else spat_threshold

        # Build metrics lookup
        metrics_map: Dict[str, SymbolMetrics] = {}
        if request and hasattr(request, 'metrics') and request.metrics:
            for sym, m in request.metrics.items():
                metrics_map[sym.upper()] = m

        scored_candidates: List[Tuple[float, Decision, Dict[str, Any]]] = []
        filtered_out: List[Decision] = []

        for sig in signals:
            ticker = sig.get('ticker', '').strip().upper()
            pattern_score = float(sig.get('score', 0) or 0)

            # ── EXCLUDED LIST CHECK ────────────────────────
            try:
                from app.trading.order_guard import is_excluded
                if is_excluded(ticker):
                    logger.info(f"[PATADD] ⛔ {ticker}: EXCLUDED — skipping (qe_excluded.csv)")
                    continue
            except Exception:
                pass

            # ── FILTER 0: Minimum holding days remaining ─────
            # Pattern exit date must be at least 3 days away
            remaining_days = 0
            try:
                exit_date_str = sig.get('exit_date', '')
                if exit_date_str:
                    import pandas as pd
                    exit_dt = pd.Timestamp(exit_date_str)
                    today = pd.Timestamp(datetime.now().replace(
                        hour=0, minute=0, second=0, microsecond=0))
                    remaining_days = (exit_dt - today).days
            except Exception:
                remaining_days = 99  # Can't determine, let it pass

            if remaining_days < min_holding_days:
                filtered_out.append(Decision(
                    symbol=ticker, action="FILTERED", filtered_out=True,
                    filter_reasons=[
                        f"Only {remaining_days}d remaining until pattern exit "
                        f"(min {min_holding_days}d required)"
                    ],
                    engine_name="PATADD",
                    timestamp=datetime.now(),
                ))
                continue

            # ── Get QE metric ────────────────────────────────
            metric = metrics_map.get(ticker)

            # Enrich from signal if metric not in request
            fbtot = None
            sfstot = None
            gort = None
            sma63_chg = None
            bid_buy_ucuzluk = None
            ask_sell_pahalilik = None
            bid = float(sig.get('bid', 0) or 0)
            ask = float(sig.get('ask', 0) or 0)
            last_price = float(sig.get('last', 0) or 0)
            maxalw = 0
            avg_adv = 0.0
            spread = 0.0

            if metric:
                fbtot = getattr(metric, 'fbtot', None)
                sfstot = getattr(metric, 'sfstot', None)
                gort = getattr(metric, 'gort', None)
                sma63_chg = getattr(metric, 'sma63_chg', None)
                bid_buy_ucuzluk = getattr(metric, 'bid_buy_ucuzluk', None)
                ask_sell_pahalilik = getattr(metric, 'ask_sell_pahalilik', None)
                maxalw = int(getattr(metric, 'maxalw', 0) or 0)
                avg_adv = float(getattr(metric, 'avg_adv', 0) or 0)
                if bid == 0:
                    bid = float(getattr(metric, 'bid', 0) or 0)
                if ask == 0:
                    ask = float(getattr(metric, 'ask', 0) or 0)
                if last_price == 0:
                    last_price = float(getattr(metric, 'last', 0) or 0)
                spread = float(getattr(metric, 'spread', 0) or 0)
            else:
                # Fallback from enriched signal
                fbtot = float(sig.get('Fbtot', 0) or 0) or None
                sfstot = float(sig.get('SFStot', 0) or 0) or None
                gort = float(sig.get('GORT', 0) or 0) or None
                sma63_chg = float(sig.get('SMA63chg', 0) or 0) or None

            # ── FILTER 1: Critical metric null check ─────────
            logger.info(
                f"[PATADD_DEBUG] {label} {ticker}: metric_found={metric is not None}, "
                f"fbtot={fbtot}, sfstot={sfstot}, gort={gort}, "
                f"bid_buy_ucuzluk={bid_buy_ucuzluk}, ask_sell_pahalilik={ask_sell_pahalilik}, "
                f"bid={bid}, ask={ask}, last={last_price}, "
                f"pattern_score={pattern_score}"
            )
            if direction == 'LONG':
                if fbtot is None or bid_buy_ucuzluk is None:
                    filtered_out.append(Decision(
                        symbol=ticker, action="FILTERED", filtered_out=True,
                        filter_reasons=[f"PATADD {label}: Critical metrics MISSING (fbtot={fbtot}, bid_buy={bid_buy_ucuzluk})"],
                        reject_reason_code=RejectReason.CRITICAL_METRIC_MISSING,
                        engine_name="PATADD",
                        timestamp=datetime.now(),
                    ))
                    continue
            else:
                if sfstot is None or ask_sell_pahalilik is None:
                    filtered_out.append(Decision(
                        symbol=ticker, action="FILTERED", filtered_out=True,
                        filter_reasons=[f"PATADD {label}: Critical metrics MISSING (sfstot={sfstot}, ask_sell={ask_sell_pahalilik})"],
                        reject_reason_code=RejectReason.CRITICAL_METRIC_MISSING,
                        engine_name="PATADD",
                        timestamp=datetime.now(),
                    ))
                    continue

            # ── FILTER 2: Fbtot / SFStot threshold ───────────
            # LONG:  Fbtot > 1.10 → hisse grupta UCUZ = iyi long
            # SHORT: SFStot < 1.10 → hisse grupta PAHALİ = iyi short
            #        (JanallApp default: "below" filtre → düşük SFStot = iyi short)
            if direction == 'LONG':
                if fbtot <= fbtot_gt:
                    filtered_out.append(Decision(
                        symbol=ticker, action="FILTERED", filtered_out=True,
                        filter_reasons=[f"Fbtot {fbtot:.2f} <= {fbtot_gt} (not cheap enough for LONG)"],
                        reject_reason_code=RejectReason.NOT_CHEAP_ENOUGH,
                        reject_reason_details={'value': fbtot, 'limit': fbtot_gt},
                        engine_name="PATADD",
                        timestamp=datetime.now(),
                    ))
                    continue
            else:
                # SHORT: SFStot must be BELOW threshold (düşük = pahalı = iyi short)
                if sfstot >= sfstot_lt:
                    filtered_out.append(Decision(
                        symbol=ticker, action="FILTERED", filtered_out=True,
                        filter_reasons=[
                            f"SFStot {sfstot:.2f} >= {sfstot_lt} "
                            f"(not expensive enough — low SFStot = good short)"
                        ],
                        reject_reason_code=RejectReason.NOT_EXPENSIVE_ENOUGH,
                        reject_reason_details={'value': sfstot, 'limit': sfstot_lt},
                        engine_name="PATADD",
                        timestamp=datetime.now(),
                    ))
                    continue

            # ── FILTER 2b: Intraday ucuzluk/pahalilik ────────
            # LONG: bid_buy_ucuzluk < -0.06 (stock is now cheap)
            # SHORT: ask_sell_pahalilik > 0.06 (stock is now expensive)
            if direction == 'LONG':
                if bid_buy_ucuzluk >= bid_buy_ucuzluk_lt:
                    filtered_out.append(Decision(
                        symbol=ticker, action="FILTERED", filtered_out=True,
                        filter_reasons=[
                            f"Bid Buy Ucuzluk {bid_buy_ucuzluk:.4f} >= {bid_buy_ucuzluk_lt} "
                            f"(not cheap enough intraday)"
                        ],
                        reject_reason_code=RejectReason.NOT_CHEAP_ENOUGH,
                        reject_reason_details={'value': bid_buy_ucuzluk, 'limit': bid_buy_ucuzluk_lt},
                        engine_name="PATADD",
                        timestamp=datetime.now(),
                    ))
                    continue
            else:
                if ask_sell_pahalilik <= ask_sell_pahalilik_gt:
                    filtered_out.append(Decision(
                        symbol=ticker, action="FILTERED", filtered_out=True,
                        filter_reasons=[
                            f"Ask Sell Pahalilik {ask_sell_pahalilik:.4f} <= {ask_sell_pahalilik_gt} "
                            f"(not expensive enough intraday)"
                        ],
                        reject_reason_code=RejectReason.NOT_EXPENSIVE_ENOUGH,
                        reject_reason_details={'value': ask_sell_pahalilik, 'limit': ask_sell_pahalilik_gt},
                        engine_name="PATADD",
                        timestamp=datetime.now(),
                    ))
                    continue

            # ── FILTER 2c: GORT directional check ────────────
            # LONG: GORT < 1.0 → grupta çok öne çıkmamış = giriş fırsatı
            # SHORT: GORT > -1.0 → grupta çok geri kalmamış = short fırsatı
            # GORT = 0 veya None → filtre yoksayılır
            if gort is not None and gort != 0:
                if direction == 'LONG' and gort >= 1.5:
                    filtered_out.append(Decision(
                        symbol=ticker, action="FILTERED", filtered_out=True,
                        filter_reasons=[
                            f"GORT={gort:.3f} >= 1.5 (grupta çok öne çıkmış, "
                            f"LONG için GORT < 1.5 olmalı)"
                        ],
                        reject_reason_code=RejectReason.NOT_CHEAP_ENOUGH,
                        reject_reason_details={'value': gort, 'limit': 1.0},
                        engine_name="PATADD",
                        timestamp=datetime.now(),
                    ))
                    continue
                elif direction == 'SHORT' and gort <= -1.5:
                    filtered_out.append(Decision(
                        symbol=ticker, action="FILTERED", filtered_out=True,
                        filter_reasons=[
                            f"GORT={gort:.3f} <= -1.5 (grupta çok geri kalmış, "
                            f"SHORT için GORT > -1.5 olmalı)"
                        ],
                        reject_reason_code=RejectReason.NOT_EXPENSIVE_ENOUGH,
                        reject_reason_details={'value': gort, 'limit': -1.0},
                        engine_name="PATADD",
                        timestamp=datetime.now(),
                    ))
                    continue

            # ── FILTER 3: Existing position limit ────────────
            existing_qty = existing_map.get(ticker, 0)
            if direction == 'LONG':
                existing_abs = abs(existing_qty) if existing_qty > 0 else 0
            else:
                existing_abs = abs(existing_qty) if existing_qty < 0 else 0

            # MAXALW limit: Pre-filter with max possible recpat (2.0)
            # Actual recpat-based limit applied later in lot calculation
            if maxalw > 0 and existing_abs >= int(maxalw * 2.0):
                filtered_out.append(Decision(
                    symbol=ticker, action="FILTERED", filtered_out=True,
                    filter_reasons=[f"Existing position {existing_abs} >= MAX_PATADD_LIMIT {int(maxalw * 2.0)} (MAXALW={maxalw} × 2.0 max recpat)"],
                    reject_reason_code=RejectReason.EXISTING_POSITION_LIMIT,
                    engine_name="PATADD",
                    timestamp=datetime.now(),
                ))
                continue

            # ── CALCULATE COMPOSITE SCORE ────────────────────
            # LPAT = PatternScore × Fbtot  (high Fbtot = ucuz = iyi long → yüksek skor)
            # SPAT = PatternScore / SFStot  (low SFStot = pahalı = iyi short → yüksek skor)
            if direction == 'LONG':
                qe_val = fbtot
                pat_score = pattern_score * qe_val
            else:
                # SFStot küçükse iyi short → 1/SFStot ile çarparak
                # düşük SFStot'u yüksek SPAT score'a çeviriyoruz
                qe_val = sfstot
                pat_score = pattern_score / max(qe_val, 0.01)  # Guard div-by-zero

            # ── FILTER: LPAT/SPAT composite score threshold ───
            # LPAT >= 45 (LONG), SPAT >= 30 (SHORT)
            if pat_score < score_threshold:
                filtered_out.append(Decision(
                    symbol=ticker, action="FILTERED", filtered_out=True,
                    filter_reasons=[
                        f"{label}={pat_score:.1f} < threshold {score_threshold:.0f} "
                        f"(PatScore={pattern_score:.1f}, {'Fbtot' if direction == 'LONG' else 'SFStot'}={qe_val:.2f})"
                    ],
                    reject_reason_code=RejectReason.NOT_CHEAP_ENOUGH,
                    reject_reason_details={'value': pat_score, 'limit': score_threshold},
                    engine_name="PATADD",
                    timestamp=datetime.now(),
                ))
                continue

            # ── LOT CALCULATION (Score-weighted MAXALW — recpat) ──────
            # recpat = LPAT/SPAT normalized MAXALW multiplier
            # LPAT/SPAT range ~45-150 (pipeline_score × Fbtot or / SFStot)
            # pat_score / 40 gives: LPAT 20→0.50, 40→1.0, 60→1.5, 80+→2.0
            # Yüksek LPAT = ucuz + güçlü pattern → daha büyük pozisyon
            # Yüksek SPAT = pahalı + güçlü pattern → daha büyük short
            if maxalw <= 0:
                maxalw = max_lot_per_symbol  # fallback

            # RECPAT: LPAT/SPAT composite score'a göre MAXALW çarpanı
            recpat = max(0.5, min(2.0, pat_score / 40.0))
            patadd_maxalw_raw = int(maxalw * recpat)

            # ═══════════════════════════════════════════════════════════════
            # HARD CAP: patadd_maxalw may NEVER exceed base MAXALW × 1.5
            # Without this cap, high pattern scores (60+) could push
            # patadd_maxalw to 170%+ of base (e.g. 2000 → 3400), allowing
            # runaway position accumulation across cycles.
            # ═══════════════════════════════════════════════════════════════
            PATADD_MAXALW_HARD_CAP_MULT = 1.5
            patadd_maxalw_cap = int(maxalw * PATADD_MAXALW_HARD_CAP_MULT)
            patadd_maxalw = min(patadd_maxalw_raw, patadd_maxalw_cap)

            if patadd_maxalw < patadd_maxalw_raw:
                logger.warning(
                    f"[PATADD] {label} {ticker}: patadd_maxalw HARD-CAPPED "
                    f"{patadd_maxalw_raw} → {patadd_maxalw} "
                    f"(cap={PATADD_MAXALW_HARD_CAP_MULT}× base MAXALW={maxalw})"
                )

            logger.info(
                f"[PATADD] {label} {ticker}: recpat={recpat:.2f} "
                f"({label}={pat_score:.1f}/40) → patadd_maxalw={patadd_maxalw} "
                f"(base MAXALW={maxalw}, cap={patadd_maxalw_cap})"
            )

            portfolio_percent = (existing_abs / patadd_maxalw) * 100 if patadd_maxalw > 0 else 0

            # Find applicable portfolio rule
            applicable_rule = None
            for rule in self._portfolio_rules:
                if portfolio_percent < rule['max_portfolio_percent']:
                    applicable_rule = rule
                    break
            if not applicable_rule:
                applicable_rule = self._portfolio_rules[-1]

            base_lot = patadd_maxalw * applicable_rule['maxalw_multiplier']

            # MAXALW remaining cap (boosted limit)
            maxalw_remaining = max(0, patadd_maxalw - existing_abs)
            raw_lot = min(base_lot, maxalw_remaining)

            # Strict rounding (min 200 for BUY, same as ADDNEWPOS v3.0)
            lot_policy = {'min_buy_lot': min_lot, 'round_to': self.LOT_ROUNDING}
            final_lot = calculate_rounded_lot(raw_lot, lot_policy, existing_qty=0, action="BUY")

            if final_lot < min_lot:
                filtered_out.append(Decision(
                    symbol=ticker, action="FILTERED", filtered_out=True,
                    filter_reasons=[f"Lot {final_lot} < min {min_lot} (MAXALW_remaining={maxalw_remaining})"],
                    reject_reason_code=RejectReason.EXISTING_POSITION_LIMIT,
                    engine_name="PATADD",
                    timestamp=datetime.now(),
                ))
                continue

            # ── Build Decision (same format as ADDNEWPOS) ────
            if direction == 'LONG':
                action = "ADD" if existing_qty > 0 else "BUY"
                order_type = "BID_BUY"
                price_hint = bid if bid > 0 else last_price
                # Passive price: bid + spread*15%
                if bid > 0 and spread > 0:
                    price_hint = round(bid + spread * 0.15, 2)
            else:
                action = "ADD_SHORT" if existing_qty < 0 else "SHORT"
                order_type = "ASK_SELL"
                price_hint = ask if ask > 0 else last_price
                if ask > 0 and spread > 0:
                    price_hint = round(ask - spread * 0.15, 2)

            reason = (
                f"PATADD {label}: PatScore={pattern_score:.1f} × "
                f"{'Fbtot' if direction == 'LONG' else 'SFStot'}={qe_val:.2f} "
                f"= {pat_score:.1f} | "
                f"Strategy={sig.get('strategy', '')} | "
                f"WinRate={sig.get('win_rate', 0):.0f}%"
            )

            decision = Decision(
                symbol=ticker,
                action=action,
                order_type=order_type,
                strategy_tag=f"LT_PA_{'LONG' if direction == 'LONG' else 'SHORT'}_INC",
                calculated_lot=final_lot,
                price_hint=price_hint,
                step_number=1,
                reason=reason,
                engine_name="PATADD",
                confidence=min(1.0, pat_score / 100.0),
                metrics_used={
                    'pat_score': pat_score,
                    'pattern_score': pattern_score,
                    'fbtot': fbtot,
                    'sfstot': sfstot,
                    'gort': gort,
                    'sma63_chg': sma63_chg,
                    'bid_buy_ucuzluk': bid_buy_ucuzluk,
                    'ask_sell_pahalilik': ask_sell_pahalilik,
                    'maxalw': maxalw,
                    'avg_adv': avg_adv,
                    'existing_qty': existing_qty,
                    'win_rate': sig.get('win_rate', 0),
                    'sharpe': sig.get('sharpe', 0),
                    'strategy': sig.get('strategy', ''),
                    'entry_date': sig.get('entry_date', ''),
                    'exit_date': sig.get('exit_date', ''),
                    'expected_return': sig.get('expected_return', 0),
                },
                priority=17,
                timestamp=datetime.now(),
            )

            # Store with score for ranking
            scored_candidates.append((pat_score, decision, sig))

        # ── RANK by LPAT/SPAT score (NOT DOSGRUP diversification) ──
        scored_candidates.sort(key=lambda x: x[0], reverse=True)

        # Take top N
        decisions = []
        for i, (score, dec, sig) in enumerate(scored_candidates):
            if i >= max_orders:
                filtered_out.append(Decision(
                    symbol=dec.symbol, action="FILTERED", filtered_out=True,
                    filter_reasons=[f"Exceeded max_orders_per_side={max_orders} (rank={i+1}, {label}={score:.1f})"],
                    engine_name="PATADD",
                    timestamp=datetime.now(),
                ))
                continue
            decisions.append(dec)
            logger.info(
                f"[PATADD] ✅ {label} PASSED {dec.symbol}: {dec.action} {dec.calculated_lot} lot "
                f"| pat={score:.1f} fbtot={fbtot} sfstot={sfstot} gort={gort} "
                f"ucuz={bid_buy_ucuzluk} pah={ask_sell_pahalilik} "
                f"bid={bid} ask={ask} last={last_price} "
                f"son5={metric.son5_tick if metric else None} v1h={metric.volav_1h if metric else None} v4h={metric.volav_4h if metric else None}"
            )

        total_lots = sum(d.calculated_lot or 0 for d in decisions)
        # Log filter reasons for each filtered candidate
        for f_dec in filtered_out:
            reasons = ', '.join(f_dec.filter_reasons) if hasattr(f_dec, 'filter_reasons') and f_dec.filter_reasons else 'unknown'
            # Get metrics for this symbol
            _fm = metrics_map.get(f_dec.symbol)
            _fms = ""
            if _fm:
                _fms = (
                    f" | fbtot={_fm.fbtot} sfstot={_fm.sfstot} gort={_fm.gort} "
                    f"ucuz={_fm.bid_buy_ucuzluk} pah={_fm.ask_sell_pahalilik} "
                    f"bid={_fm.bid} ask={_fm.ask} last={_fm.last} "
                    f"son5={_fm.son5_tick} v1h={_fm.volav_1h} v4h={_fm.volav_4h}"
                )
            logger.info(
                f"[PATADD] {label} FILTERED {f_dec.symbol}: {reasons}{_fms}"
            )
        logger.info(
            f"[PATADD] {label}: {len(decisions)} decisions ({total_lots} lots), "
            f"{len(filtered_out)} filtered"
        )
        return decisions, filtered_out


# ────────────────────────────────────────────────────────────────────
# Global Instance
# ────────────────────────────────────────────────────────────────────

_patadd_engine: Optional[PataddEngine] = None


def get_patadd_engine() -> PataddEngine:
    """Get (or create) the global PataddEngine instance."""
    global _patadd_engine
    if _patadd_engine is None:
        _patadd_engine = PataddEngine()
    return _patadd_engine
