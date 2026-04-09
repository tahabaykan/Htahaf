"""
ADDNEWPOS Decision Engine - Janall-Compatible v3.0

ADDNEWPOS (Add New Position) decision engine for opening new positions.
Supports both LONG and SHORT positions (AddLong and AddShort modes).

v3.0 CHANGES (Birebir JanallApp Mantığı):
- tumcsvlong.csv ve tumcsvshort.csv'den doğrudan okur
- compute_lt_goodness KALDIRILDI - goodness skoru yok
- pick_candidates_by_intent KALDIRILDI - tumcsv sıralaması kullanılır
- Lot hesabı: RECSIZE (tumcsv'den) + MAXALW kuralları
- Intent model sadece gating için kalır (kaç hisse seçilecek)
- İntraday filtreler (Fbtot, SFStot, ucuzluk, pahalilik) korunur
"""

from loguru import logger
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any

from app.psfalgo.decision_models import (
    Decision,
    DecisionRequest,
    DecisionResponse,
    PositionSnapshot,
    ExposureSnapshot,
    SymbolMetrics,
)

# Intent Math (sadece gating: exposure regime → pick_count)
from app.psfalgo.intent_math import (
    compute_intents,
    calculate_rounded_lot,
    clamp_no_flip,
    clamp_post_trade_hold
)

from app.psfalgo.decision_models import RejectReason
from app.psfalgo.reject_reason_store import get_reject_reason_store



# tumcsv dosyalarinin konumu
TUMCSV_DIR = Path(r"C:\StockTracker\janall")


class AddnewposEngine:
    """
    ADDNEWPOS Decision Engine - Birebir JanallApp mantığı.
    
    tumcsvlong.csv ve tumcsvshort.csv'den önceden seçilmiş hisseleri okur.
    İntraday filtreler uygular (Fbtot, SFStot, ucuzluk, pahalilik).
    Lot hesabı: RECSIZE (tumcsv'den) + MAXALW portfolio kuralları.
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize ADDNEWPOS Engine.
        """
        self.config_path = config_path
        self.settings = {}
        self.addlong_config = {}
        self.addshort_config = {}
        self.portfolio_rules = []
        self.lot_policy_config = {}
        self.intent_model_config = {}
        self.exposure_usage_percent = 70.0
        
        # Load rules (yaml if available, otherwise defaults)
        self._load_rules()
        
        # Load tumcsv data
        self._tumcsv_long = None
        self._tumcsv_short = None
        self._tumcsv_loaded_date = None
        
        logger.info("[ADDNEWPOS] Engine initialized (Janall v3.0 - tumcsv mode)")

    def _load_rules(self):
        """Load rules from psfalgo_rules.yaml"""
        try:
            if self.config_path and self.config_path.exists():
                import yaml
                with open(self.config_path) as f:
                    all_rules = yaml.safe_load(f)
                
                if all_rules and 'ADDNEWPOS' in all_rules:
                    rules = all_rules['ADDNEWPOS']
                    self.settings = rules.get('settings', {})
                    self.addlong_config = rules.get('AddLong', {})
                    self.addshort_config = rules.get('AddShort', {})
                    self.portfolio_rules = rules.get('janall_portfolio_rules', [])
                    self.lot_policy_config = rules.get('lot_policy', {})
                    self.intent_model_config = rules.get('intent_model', {})
                    self.exposure_usage_percent = self.settings.get('exposure_usage_percent', 70.0)
                    logger.info(f"[ADDNEWPOS] Loaded rules from {self.config_path}")
                    return
        except Exception as e:
            logger.warning(f"[ADDNEWPOS] Could not load rules: {e}")
        
        # Set defaults
        self._set_default_rules()

    def _set_default_rules(self):
        """Set default rules (Janall-compatible)"""
        self.settings = {
            'mode': 'both',
            'default_lot': 200,
            'min_lot_size': 200,
            'exposure_usage_percent': 70.0,
        }
        
        self.addlong_config = {
            'enabled': True,
            'filters_disabled': False,
            'filters': {
                'bid_buy_ucuzluk_lt': -0.02,
                'fbtot_gt': 1.10,
            }
        }
        
        self.addshort_config = {
            'enabled': True,
            'filters_disabled': False,
            'filters': {
                'ask_sell_pahalilik_gt': 0.02,
                'sfstot_lt': 1.10,
            }
        }
        
        self.portfolio_rules = [
            {'max_portfolio_percent': 1, 'maxalw_multiplier': 0.50, 'portfolio_percent': 5},
            {'max_portfolio_percent': 3, 'maxalw_multiplier': 0.40, 'portfolio_percent': 4},
            {'max_portfolio_percent': 5, 'maxalw_multiplier': 0.30, 'portfolio_percent': 3},
            {'max_portfolio_percent': 7, 'maxalw_multiplier': 0.20, 'portfolio_percent': 2},
            {'max_portfolio_percent': 10, 'maxalw_multiplier': 0.10, 'portfolio_percent': 1.5},
            {'max_portfolio_percent': 100, 'maxalw_multiplier': 0.05, 'portfolio_percent': 1},
        ]
        
        self.lot_policy_config = {
            'min_buy_lot': 200,
            'round_to': 100,
        }
        
        # Intent model config — keys MUST match compute_intents() parameters:
        #   hard_threshold_pct: Exposure % above which AddIntent = 0 (HARD regime)
        #   soft_ratio_num/den: S = H * (num/den), transition zone start
        #   Amax: Maximum AddIntent in NORMAL zone (100 = full throttle)
        #   Asoft: AddIntent at the boundary of NORMAL → SOFT (20 = cautious)
        #   pn, q, ps: Shape exponents for the piecewise curves
        self.intent_model_config = {
            'hard_threshold_pct': 92.0,   # Hard cutoff at 92% exposure
            'soft_ratio_num': 12,         # S = 92 * 12/13 ≈ 84.9%
            'soft_ratio_den': 13,
            'Amax': 100.0,               # Full intent at low exposure
            'Asoft': 20.0,               # Cautious intent at soft boundary
            'pn': 1.25,                  # Normal zone decay exponent
            'q': 2.14,                   # Normal zone steepness
            'ps': 1.50,                  # Soft zone decay exponent
        }
        
        self.exposure_usage_percent = 70.0

    # ═══════════════════════════════════════════════════════════════════
    # TUMCSV DATA LOADER
    # ═══════════════════════════════════════════════════════════════════
    
    def _load_tumcsv_data(self):
        """
        tumcsvlong.csv ve tumcsvshort.csv'yi oku.
        Bu dosyalar ntumcsvport.py tarafından run_daily_n.py pipeline'inda üretilir.
        FINAL_THG'ye göre sıralı (LONG desc, SHORT asc).
        """
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Günde bir kez yükle
        if self._tumcsv_loaded_date == today and self._tumcsv_long is not None:
            return
        
        # LONG
        long_path = TUMCSV_DIR / "tumcsvlong.csv"
        if long_path.exists():
            try:
                self._tumcsv_long = pd.read_csv(str(long_path))
                # FINAL_THG'ye göre sırala (yüksek = iyi long)
                if 'FINAL_THG' in self._tumcsv_long.columns:
                    self._tumcsv_long = self._tumcsv_long.sort_values('FINAL_THG', ascending=False)
                logger.info(f"[ADDNEWPOS] tumcsvlong loaded: {len(self._tumcsv_long)} stocks")
            except Exception as e:
                logger.error(f"[ADDNEWPOS] Failed to load tumcsvlong: {e}")
                self._tumcsv_long = pd.DataFrame()
        else:
            logger.warning(f"[ADDNEWPOS] tumcsvlong.csv not found at {long_path}")
            self._tumcsv_long = pd.DataFrame()
        
        # SHORT
        short_path = TUMCSV_DIR / "tumcsvshort.csv"
        if short_path.exists():
            try:
                self._tumcsv_short = pd.read_csv(str(short_path))
                # SHORT_FINAL'e göre sırala (düşük = iyi short)
                if 'SHORT_FINAL' in self._tumcsv_short.columns:
                    self._tumcsv_short = self._tumcsv_short.sort_values('SHORT_FINAL', ascending=True)
                logger.info(f"[ADDNEWPOS] tumcsvshort loaded: {len(self._tumcsv_short)} stocks")
            except Exception as e:
                logger.error(f"[ADDNEWPOS] Failed to load tumcsvshort: {e}")
                self._tumcsv_short = pd.DataFrame()
        else:
            logger.warning(f"[ADDNEWPOS] tumcsvshort.csv not found at {short_path}")
            self._tumcsv_short = pd.DataFrame()
        
        self._tumcsv_loaded_date = today

    def _get_tumcsv_symbols(self, side: str) -> List[Dict]:
        """
        tumcsv'den hisse listesini al. Sıralı gelir (FINAL_THG desc / SHORT_FINAL asc).
        Her element: {'symbol': ..., 'FINAL_THG': ..., 'SHORT_FINAL': ..., 'RECSIZE': ..., 'DOSYA': ..., ...}
        """
        self._load_tumcsv_data()
        
        if side == "LONG" and self._tumcsv_long is not None and not self._tumcsv_long.empty:
            result = []
            for _, row in self._tumcsv_long.iterrows():
                sym = str(row.get('PREF_IBKR', '')).strip()
                if not sym:
                    continue
                result.append({
                    'symbol': sym,
                    'FINAL_THG': float(row.get('FINAL_THG', 0) or 0),
                    'SHORT_FINAL': float(row.get('SHORT_FINAL', 0) or 0),
                    'RECSIZE': int(float(row.get('RECSIZE', 200) or 200)),
                    'AVG_ADV': float(row.get('AVG_ADV', 0) or 0),
                    'KUME_PREM': float(row.get('KUME_PREM', 0) or 0),
                    'KUME_ORT': float(row.get('KUME_ORT', 0) or 0),
                    'DOSYA': str(row.get('DOSYA', '')),
                    'CGRUP': str(row.get('CGRUP', '')),
                    'LONG_KURAL': str(row.get('LONG_KURAL', '')),
                })
            return result
        
        elif side == "SHORT" and self._tumcsv_short is not None and not self._tumcsv_short.empty:
            result = []
            for _, row in self._tumcsv_short.iterrows():
                sym = str(row.get('PREF_IBKR', '')).strip()
                if not sym:
                    continue
                result.append({
                    'symbol': sym,
                    'FINAL_THG': float(row.get('FINAL_THG', 0) or 0),
                    'SHORT_FINAL': float(row.get('SHORT_FINAL', 0) or 0),
                    'RECSIZE': int(float(row.get('RECSIZE', 200) or 200)),
                    'AVG_ADV': float(row.get('AVG_ADV', 0) or 0),
                    'KUME_PREM': float(row.get('KUME_PREM', 0) or 0),
                    'KUME_ORT': float(row.get('KUME_ORT', 0) or 0),
                    'DOSYA': str(row.get('DOSYA', '')),
                    'CGRUP': str(row.get('CGRUP', '')),
                    'SHORT_KURAL': str(row.get('SHORT_KURAL', '')),
                })
            return result
        
        return []

    # ═══════════════════════════════════════════════════════════════════
    # ELIGIBILITY CHECK
    # ═══════════════════════════════════════════════════════════════════
    
    def is_eligible(self, exposure: Optional[ExposureSnapshot], exposure_mode: Optional[str] = None) -> Tuple[bool, str]:
        """Check if ADDNEWPOS should run based on exposure."""
        if not exposure:
            return False, "No exposure data"
        
        if exposure_mode and exposure_mode.upper() in ['DEFANSIF', 'HEAVY']:
            return False, f"Mode={exposure_mode} blocks new positions"
        
        if exposure.pot_total is not None and exposure.pot_max is not None:
            if exposure.pot_total >= exposure.pot_max:
                return False, "Portfolio full (pot_total >= pot_max)"
        
        return True, "OK"

    # ═══════════════════════════════════════════════════════════════════
    # MAIN ENTRY POINT
    # ═══════════════════════════════════════════════════════════════════
    
    async def addnewpos_decision_engine(self, request: DecisionRequest) -> DecisionResponse:
        """
        ADDNEWPOS decision engine - main entry point.
        
        v3.0: tumcsvlong/tumcsvshort'tan okur, JanallApp birebir mantık.
        """
        start_time = datetime.now()
        
        try:
            # Check eligibility
            exposure_mode = request.exposure.mode if request.exposure else None
            logger.info(
                f"[ADDNEWPOS] Exposure diagnostic: mode={exposure_mode}, "
                f"pot_total={request.exposure.pot_total if request.exposure else 'N/A'}, "
                f"pot_max={request.exposure.pot_max if request.exposure else 'N/A'}"
            )
            is_eligible, eligibility_reason = self.is_eligible(request.exposure, exposure_mode)
            logger.info(f"[ADDNEWPOS] Eligibility: {is_eligible} ({eligibility_reason})")
            
            # CleanLogs
            try:
                from app.psfalgo.clean_log_store import get_clean_log_store, LogSeverity, LogEvent
                from dataclasses import asdict
                clean_log = get_clean_log_store()
                from app.trading.trading_account_context import get_trading_context
                ctx = get_trading_context()
                account_id = ctx.trading_mode.value
            except:
                clean_log = None
                account_id = "UNKNOWN"

            if not is_eligible:
                logger.info(f"[ADDNEWPOS] Not eligible: {eligibility_reason}")
                if clean_log:
                    clean_log.log_event(
                        account_id=account_id, component="ADDNEWPOS_ENGINE",
                        event=LogEvent.SKIP.value, symbol=None,
                        message=f"Skipped: {eligibility_reason}",
                        severity=LogSeverity.INFO.value,
                        correlation_id=request.correlation_id,
                        details={'reason': eligibility_reason}
                    )
                return DecisionResponse(
                    decisions=[], filtered_out=[],
                    step_summary={'eligibility': {'eligible': False, 'reason': eligibility_reason}},
                    execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                    correlation_id=request.correlation_id
                )
            
            all_decisions = []
            all_filtered_out = []
            step_summary = {'eligibility': {'eligible': True, 'reason': eligibility_reason}}
            
            # ═══════════════════════════════════════════════════════════
            # INTENT MODEL: Sadece gating (kaç hisse seçilecek)
            # ═══════════════════════════════════════════════════════════
            exposure_pct = 0.0
            if request.exposure and request.exposure.pot_max > 0:
                exposure_pct = (request.exposure.pot_total / request.exposure.pot_max) * 100.0
            
            add_intent, reduce_intent, regime = compute_intents(exposure_pct, self.intent_model_config)
            
            step_summary['intent_model'] = {
                'exposure_pct': exposure_pct,
                'add_intent': add_intent,
                'regime': regime,
            }
            
            # Gating: HARD regime veya çok düşük intent → çık
            if regime == 'HARD' or add_intent < 0.1:
                logger.info(f"[ADDNEWPOS] Intent blocking: Regime={regime}, AddIntent={add_intent:.2f}")
                return DecisionResponse(
                    decisions=[], filtered_out=[],
                    step_summary=step_summary,
                    execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                    correlation_id=request.correlation_id
                )
            
            # Pick count: Intent'e göre kaç hisse seçeceğiz
            # tumcsv zaten önceden hazırlanmış EN İYİ adayları içerir.
            # Intent modeli çok kısıtlayıcı olmamalı — tüm adayları dene,
            # intraday filtreler (Fbtot, ucuzluk, pahalilik) zaten eleme yapar.
            if add_intent > 45: pick_count = 40
            elif add_intent > 25: pick_count = 25
            elif add_intent > 10: pick_count = 10
            else: pick_count = 0
            
            logger.info(f"[ADDNEWPOS] Intent={add_intent:.0f}, Regime={regime}, PickCount={pick_count}")
            
            # Cooldown & Confidence
            from app.psfalgo.decision_cooldown import get_decision_cooldown_manager
            from app.psfalgo.confidence_calculator import get_confidence_calculator
            cooldown_manager = get_decision_cooldown_manager()
            confidence_calculator = get_confidence_calculator()
            
            # Remaining exposure
            remaining_exposure = 0
            if request.exposure and request.exposure.pot_max > 0:
                pot_total = request.exposure.pot_total or 0.0
                remaining_exposure = (request.exposure.pot_max - pot_total) * (self.exposure_usage_percent / 100.0)
            
            # Total portfolio lots
            total_portfolio_lots = None
            if request.exposure:
                ll = request.exposure.long_lots or 0.0
                sl = request.exposure.short_lots or 0.0
                total_portfolio_lots = ll + sl
            
            # Existing positions map
            existing_map = {}
            for pos in request.positions:
                pot = getattr(pos, 'potential_qty', pos.qty) or pos.qty
                existing_map[pos.symbol] = pot
            
            mode = self.settings.get('mode', 'both')
            
            # ═══════════════════════════════════════════════════════════
            # 🔥 JANALL CACHE ENRICHMENT — Taze metrik çek
            # KARBOTU / LT_TRIM ile aynı usul: janall_engine.symbol_metrics_cache
            # request.metrics stale olabilir (RUNALL başında oluşturulmuş),
            # bu adım taze fbtot/sfstot/gort/ucuzluk/pahalilik değerlerini alır.
            # ═══════════════════════════════════════════════════════════
            try:
                from app.api.market_data_routes import get_janall_metrics_engine as _get_janall
                _janall = _get_janall()
                if _janall and hasattr(_janall, 'symbol_metrics_cache'):
                    _enriched = 0
                    _created = 0
                    # 1) Enrich existing metrics
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
                    
                    # 2) Create metrics for tumcsv candidates NOT in request.metrics
                    # (same logic as RUNALL's CREATE step)
                    all_tumcsv_symbols = set()
                    for s in self._get_tumcsv_symbols("LONG"):
                        all_tumcsv_symbols.add(s['symbol'])
                    for s in self._get_tumcsv_symbols("SHORT"):
                        all_tumcsv_symbols.add(s['symbol'])
                    
                    from app.market_data.static_data_store import get_static_store
                    _static = get_static_store()
                    
                    for _sym in all_tumcsv_symbols:
                        if _sym in request.metrics:
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
                    
                    logger.info(
                        f"[ADDNEWPOS] 🔄 Janall cache refresh: enriched={_enriched}, "
                        f"created={_created} new metrics for tumcsv candidates"
                    )
            except Exception as e:
                logger.warning(f"[ADDNEWPOS] ⚠️ Janall cache enrichment failed: {e}")
            
            # ═══════════════════════════════════════════════════════════
            # ADDLONG — tumcsvlong'dan oku
            # ═══════════════════════════════════════════════════════════
            if mode in ['addlong_only', 'both'] and self.addlong_config.get('enabled', True):
                long_stocks = self._get_tumcsv_symbols("LONG")
                long_decisions, long_filtered = await self._process_addlong_tumcsv(
                    tumcsv_stocks=long_stocks[:pick_count],  # Intent gating: sadece top N
                    metrics=request.metrics,
                    existing_map=existing_map,
                    remaining_exposure=remaining_exposure,
                    cooldown_manager=cooldown_manager,
                    confidence_calculator=confidence_calculator,
                    snapshot_ts=request.snapshot_ts,
                    total_portfolio_lots=total_portfolio_lots,
                )
                all_decisions.extend(long_decisions)
                all_filtered_out.extend(long_filtered)
                step_summary['addlong'] = {
                    'tumcsv_total': len(long_stocks),
                    'picked': min(pick_count, len(long_stocks)),
                    'decisions': len(long_decisions),
                    'filtered': len(long_filtered),
                    'top_picks': [s['symbol'] for s in long_stocks[:pick_count]],
                }
            
            # ═══════════════════════════════════════════════════════════
            # ADDSHORT — tumcsvshort'dan oku
            # ═══════════════════════════════════════════════════════════
            if mode in ['addshort_only', 'both'] and self.addshort_config.get('enabled', True):
                short_stocks = self._get_tumcsv_symbols("SHORT")
                short_decisions, short_filtered = await self._process_addshort_tumcsv(
                    tumcsv_stocks=short_stocks[:pick_count],
                    metrics=request.metrics,
                    existing_map=existing_map,
                    remaining_exposure=remaining_exposure,
                    cooldown_manager=cooldown_manager,
                    confidence_calculator=confidence_calculator,
                    snapshot_ts=request.snapshot_ts,
                    total_portfolio_lots=total_portfolio_lots,
                )
                all_decisions.extend(short_decisions)
                all_filtered_out.extend(short_filtered)
                step_summary['addshort'] = {
                    'tumcsv_total': len(short_stocks),
                    'picked': min(pick_count, len(short_stocks)),
                    'decisions': len(short_decisions),
                    'filtered': len(short_filtered),
                    'top_picks': [s['symbol'] for s in short_stocks[:pick_count]],
                }
            
            # Intent metadata
            for d in all_decisions:
                if not hasattr(d, 'metadata') or d.metadata is None:
                    d.metadata = {}
                d.metadata['intent_model'] = {
                    'add_intent': add_intent,
                    'regime': regime,
                    'pick_count': pick_count,
                }
                d.reason += f" [Intent:{add_intent:.0f} Regime:{regime}]"
            
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(f"[ADDNEWPOS] Done. Decisions: {len(all_decisions)}, Filtered: {len(all_filtered_out)}")
            
            # Push rejections
            rr_store = get_reject_reason_store()
            for d in all_filtered_out:
                rr_store.add(d)
            
            # CleanLogs
            if clean_log:
                for d in all_decisions:
                    d.correlation_id = request.correlation_id
                    clean_log.log_event(
                        account_id=account_id, component="ADDNEWPOS_ENGINE",
                        event=LogEvent.PROPOSAL.value, symbol=d.symbol,
                        message=f"Proposed {d.action} {d.calculated_lot} lots: {d.reason}",
                        severity=LogSeverity.INFO.value,
                        correlation_id=request.correlation_id,
                        details=asdict(d)
                    )
                for f in all_filtered_out:
                    f.correlation_id = request.correlation_id
                    clean_log.log_event(
                        account_id=account_id, component="ADDNEWPOS_ENGINE",
                        event=LogEvent.SKIP.value, symbol=f.symbol,
                        message=f"Skipped {f.symbol}: {f.filter_reasons[0] if f.filter_reasons else 'Unknown'}",
                        severity=LogSeverity.INFO.value,
                        correlation_id=request.correlation_id,
                        details=asdict(f)
                    )
            
            return DecisionResponse(
                decisions=all_decisions,
                filtered_out=all_filtered_out,
                step_summary=step_summary,
                execution_time_ms=execution_time,
                correlation_id=request.correlation_id
            )
            
        except Exception as e:
            logger.error(f"[ADDNEWPOS] Error: {e}", exc_info=True)
            return DecisionResponse(
                decisions=[], filtered_out=[], step_summary={},
                execution_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                error=str(e)
            )

    # ═══════════════════════════════════════════════════════════════════
    # PROCESS ADDLONG (tumcsv based)
    # ═══════════════════════════════════════════════════════════════════
    
    async def _process_addlong_tumcsv(
        self,
        tumcsv_stocks: List[Dict],
        metrics: Dict[str, SymbolMetrics],
        existing_map: Dict[str, float],
        remaining_exposure: float,
        cooldown_manager,
        confidence_calculator,
        snapshot_ts: Optional[datetime] = None,
        total_portfolio_lots: Optional[float] = None,
    ) -> Tuple[List[Decision], List[Decision]]:
        """
        tumcsvlong'dan gelen hisseleri işle.
        Sıralama zaten FINAL_THG desc (tumcsv'den).
        İntraday filtreler uygulanır (Fbtot, ucuzluk).
        Lot: RECSIZE (tumcsv'den) veya MAXALW kuralları.
        """
        decisions = []
        filtered_out = []
        
        filters_disabled = self.addlong_config.get('filters_disabled', False)
        filters = self.addlong_config.get('filters', {})
        
        if filters_disabled:
            bid_buy_ucuzluk_lt = None
            fbtot_gt = None
        else:
            bid_buy_ucuzluk_lt = filters.get('bid_buy_ucuzluk_lt', -0.02)
            fbtot_gt = filters.get('fbtot_gt', 1.10)
        
        
        for stock in tumcsv_stocks:
            symbol = stock['symbol']
            
            # ── EXCLUDED LIST CHECK ────────────────────────
            try:
                from app.trading.order_guard import is_excluded
                if is_excluded(symbol):
                    logger.info(f"[ADDNEWPOS] ⛔ {symbol}: EXCLUDED — skipping (qe_excluded.csv)")
                    continue
            except Exception:
                pass
            
            recsize = stock.get('RECSIZE', 200)
            final_thg = stock.get('FINAL_THG', 0)
            dosya = stock.get('DOSYA', '')
            
            metric = metrics.get(symbol)
            
            if not metric:
                # DEBUG: Check WHY metric is missing - is symbol in metrics keys?
                logger.warning(
                    f"[ADDNEWPOS] ❌ {symbol}: NO METRIC FOUND in request.metrics "
                    f"(tumcsv: FTHG={final_thg:.0f}, DOSYA={dosya}). "
                    f"Total metrics keys: {len(metrics)}"
                )
                filtered_out.append(Decision(
                    symbol=symbol, action="FILTERED", filtered_out=True,
                    filter_reasons=[f"Metrics yok (tumcsv: FTHG={final_thg:.0f}, DOSYA={dosya})"],
                    reject_reason_code=RejectReason.CRITICAL_METRIC_MISSING,
                    step_number=1, timestamp=datetime.now()
                ))
                continue
            
            # DEBUG: Log ALL metrics for this candidate (PATADD-style)
            # Calculate Final_BB and Final_AB scores for logging
            _fbb = None  # Final_BB_skor = FTHG - 1000 * bid_buy_ucuzluk
            _fab = None  # Final_AB_skor = FTHG - 1000 * ask_buy_ucuzluk (approx ask_sell_pahalilik)
            if metric.bid_buy_ucuzluk is not None:
                _fbb = round(final_thg - 1000 * metric.bid_buy_ucuzluk, 2)
            if metric.ask_sell_pahalilik is not None:
                _fab = round(final_thg - 1000 * metric.ask_sell_pahalilik, 2)
            _spread = round(metric.ask - metric.bid, 4) if metric.bid and metric.ask else None
            logger.info(
                f"[ADDNEWPOS_DEBUG] LONG {symbol}: metric_found=True, "
                f"fbtot={metric.fbtot}, sfstot={metric.sfstot}, gort={metric.gort}, "
                f"bid_buy_ucuzluk={metric.bid_buy_ucuzluk}, ask_sell_pahalilik={metric.ask_sell_pahalilik}, "
                f"bid={metric.bid}, ask={metric.ask}, last={metric.last}, "
                f"prev_close={metric.prev_close}, spread={_spread}, "
                f"FTHG={final_thg:.0f}, Final_BB={_fbb}, Final_AB={_fab}, "
                f"son5={metric.son5_tick}, v1h={metric.volav_1h}, v4h={metric.volav_4h}"
            )
            
            # Null check
            if metric.bid_buy_ucuzluk is None or metric.fbtot is None:
                # DEBUG: Show all available metric fields to find the missing link
                logger.warning(
                    f"[ADDNEWPOS] ❌ {symbol}: METRIC NULL — "
                    f"bid_buy_ucuzluk={metric.bid_buy_ucuzluk}, fbtot={metric.fbtot}, "
                    f"sfstot={metric.sfstot}, gort={metric.gort}, "
                    f"bid={metric.bid}, ask={metric.ask}, last={metric.last}, "
                    f"prev_close={metric.prev_close}, spread={metric.spread} "
                    f"(FTHG={final_thg:.0f})"
                )
                filtered_out.append(Decision(
                    symbol=symbol, action="FILTERED", filtered_out=True,
                    filter_reasons=[f"bid_buy={metric.bid_buy_ucuzluk}, fbtot={metric.fbtot} (FTHG={final_thg:.0f})"],
                    reject_reason_code=RejectReason.CRITICAL_METRIC_MISSING,
                    step_number=1, timestamp=datetime.now()
                ))
                continue
            
            bid_buy = metric.bid_buy_ucuzluk
            fbtot = metric.fbtot
            
            # Fbtot filtresi
            if fbtot_gt is not None and fbtot <= fbtot_gt:
                logger.info(
                    f"[ADDNEWPOS] LONG FILTERED {symbol}: Fbtot {fbtot:.2f} <= {fbtot_gt} (not cheap enough for LONG) "
                    f"| sfstot={metric.sfstot} gort={metric.gort} ucuz={bid_buy:.4f} pah={metric.ask_sell_pahalilik} "
                    f"bid={metric.bid} ask={metric.ask} last={metric.last}"
                )
                filtered_out.append(Decision(
                    symbol=symbol, action="FILTERED", filtered_out=True,
                    filter_reasons=[f"Fbtot={fbtot:.2f} <= {fbtot_gt} (FTHG={final_thg:.0f})"],
                    reject_reason_code=RejectReason.VALUATION_TOO_POOR,
                    reject_reason_details={'value': fbtot, 'limit': fbtot_gt},
                    step_number=1, timestamp=datetime.now()
                ))
                continue
            
            # Ucuzluk filtresi
            if bid_buy_ucuzluk_lt is not None and bid_buy >= bid_buy_ucuzluk_lt:
                logger.info(
                    f"[ADDNEWPOS] LONG FILTERED {symbol}: Ucuzluk {bid_buy:.4f} >= {bid_buy_ucuzluk_lt} (not cheap enough) "
                    f"| fbtot={fbtot:.2f} sfstot={metric.sfstot} gort={metric.gort} pah={metric.ask_sell_pahalilik} "
                    f"bid={metric.bid} ask={metric.ask} last={metric.last}"
                )
                filtered_out.append(Decision(
                    symbol=symbol, action="FILTERED", filtered_out=True,
                    filter_reasons=[f"Ucuzluk={bid_buy:.4f} >= {bid_buy_ucuzluk_lt} (FTHG={final_thg:.0f})"],
                    reject_reason_code=RejectReason.NOT_CHEAP_ENOUGH,
                    reject_reason_details={'value': bid_buy, 'limit': bid_buy_ucuzluk_lt},
                    step_number=1, timestamp=datetime.now()
                ))
                continue
            
            # Existing position — no hardcoded max; MinMaxArea handles todays_max_qty
            existing_qty = abs(existing_map.get(symbol, 0))
            
            # Cooldown
            if cooldown_manager and not cooldown_manager.can_make_decision(symbol, snapshot_ts):
                filtered_out.append(Decision(
                    symbol=symbol, action="FILTERED", filtered_out=True,
                    filter_reasons=["Cooldown active"],
                    reject_reason_code=RejectReason.COOLDOWN_ACTIVE,
                    step_number=1, timestamp=datetime.now()
                ))
                continue
            
            # ═══════════════════════════════════════════════════════
            # LOT HESABI: RECSIZE (tumcsv'den)
            # RECSIZE zaten ntumcsvport.py tarafından hesaplanmış:
            #   RECSIZE = (KUME_PREM * 8 + AVG_ADV/25) / 4
            #   Cap: AVG_ADV / 6
            # MAXALW kuralları ile kısıtla
            # ═══════════════════════════════════════════════════════
            calculated_lot = self._calculate_lot_janall(
                symbol=symbol,
                recsize=recsize,
                existing_qty=existing_qty,
                metric=metric,
                total_portfolio_lots=total_portfolio_lots,
            )
            
            if calculated_lot <= 0:
                continue
            
            action = "ADD" if existing_qty > 0 else "BUY"
            
            # Confidence
            confidence = 0.5
            if confidence_calculator:
                dummy_pos = PositionSnapshot(
                    symbol=symbol, qty=calculated_lot,
                    avg_price=metric.bid or 0, current_price=metric.bid or 0,
                    unrealized_pnl=0, timestamp=datetime.now()
                )
                confidence = confidence_calculator.calculate_confidence(
                    symbol=symbol, position=dummy_pos, metrics=metric,
                    action=action, reason="AddLong"
                )
            
            decision = Decision(
                symbol=symbol, action=action, order_type="BID_BUY",
                lot_percentage=None, calculated_lot=calculated_lot,
                price_hint=metric.bid, step_number=1,
                reason=f"Pos:{int(existing_qty)} | FTHG={final_thg:.0f} REC={recsize} Fbtot={fbtot:.2f} ucuz={bid_buy:.4f} [{dosya}]",
                confidence=confidence,
                metrics_used={
                    'FINAL_THG': final_thg, 'RECSIZE': recsize,
                    'bid_buy_ucuzluk': bid_buy, 'fbtot': fbtot,
                    'DOSYA': dosya, 'existing_qty': existing_qty,
                },
                timestamp=datetime.now()
            )
            decisions.append(decision)
            logger.info(
                f"[ADDNEWPOS] ✅ LONG PASSED {symbol}: {action} {calculated_lot} lot "
                f"| fbtot={fbtot:.2f} sfstot={metric.sfstot} gort={metric.gort} "
                f"ucuz={bid_buy:.4f} pah={metric.ask_sell_pahalilik} "
                f"bid={metric.bid} ask={metric.ask} last={metric.last} "
                f"son5={metric.son5_tick} v1h={metric.volav_1h} v4h={metric.volav_4h} "
                f"FTHG={final_thg:.0f} REC={recsize}"
            )
            
            if cooldown_manager:
                cooldown_manager.record_decision(symbol, snapshot_ts)
        
        logger.info(f"[ADDNEWPOS] AddLong: {len(decisions)} decisions, {len(filtered_out)} filtered")
        return decisions, filtered_out

    # ═══════════════════════════════════════════════════════════════════
    # PROCESS ADDSHORT (tumcsv based)
    # ═══════════════════════════════════════════════════════════════════
    
    async def _process_addshort_tumcsv(
        self,
        tumcsv_stocks: List[Dict],
        metrics: Dict[str, SymbolMetrics],
        existing_map: Dict[str, float],
        remaining_exposure: float,
        cooldown_manager,
        confidence_calculator,
        snapshot_ts: Optional[datetime] = None,
        total_portfolio_lots: Optional[float] = None,
    ) -> Tuple[List[Decision], List[Decision]]:
        """
        tumcsvshort'tan gelen hisseleri işle.
        Sıralama zaten SHORT_FINAL asc (tumcsv'den).
        İntraday filtreler: SFStot < 1.75 (düşük = grupta pahalı = iyi short), pahalilik > 0.02
        Lot: RECSIZE (tumcsv'den)
        """
        decisions = []
        filtered_out = []
        
        filters_disabled = self.addshort_config.get('filters_disabled', False)
        filters = self.addshort_config.get('filters', {})
        
        if filters_disabled:
            ask_sell_pahalilik_gt = None
            sfstot_lt = None
        else:
            ask_sell_pahalilik_gt = filters.get('ask_sell_pahalilik_gt', 0.02)
            sfstot_lt = filters.get('sfstot_lt', 1.75)
        
        
        for stock in tumcsv_stocks:
            symbol = stock['symbol']
            
            # ── EXCLUDED LIST CHECK ────────────────────────
            try:
                from app.trading.order_guard import is_excluded
                if is_excluded(symbol):
                    logger.info(f"[ADDNEWPOS] ⛔ {symbol}: EXCLUDED — skipping SHORT (qe_excluded.csv)")
                    continue
            except Exception:
                pass
            
            recsize = stock.get('RECSIZE', 200)
            short_final = stock.get('SHORT_FINAL', 0)
            dosya = stock.get('DOSYA', '')
            
            metric = metrics.get(symbol)
            
            if not metric:
                logger.warning(
                    f"[ADDNEWPOS] ❌ {symbol}: NO METRIC FOUND (SHORT) "
                    f"(tumcsv: SF={short_final:.0f}, DOSYA={dosya})"
                )
                filtered_out.append(Decision(
                    symbol=symbol, action="FILTERED", filtered_out=True,
                    filter_reasons=[f"Metrics yok (tumcsv: SF={short_final:.0f}, DOSYA={dosya})"],
                    reject_reason_code=RejectReason.CRITICAL_METRIC_MISSING,
                    step_number=2, timestamp=datetime.now()
                ))
                continue
            
            # DEBUG: Log ALL metrics for this candidate (PATADD-style)
            # Calculate Final_BS and Final_SAS scores for logging
            _fbs = None  # Final_BS_skor = FTHG - 1000 * bid_sell_pahalilik (approx bid_buy_ucuzluk)
            _fsas = None  # Final_SAS_skor = SF - 1000 * ask_sell_pahalilik
            _fthg_s = float(getattr(metric, 'final_thg', 0) or 0)  # try from metric
            if not _fthg_s:
                try:
                    from app.market_data.static_data_store import get_static_store
                    _ss = get_static_store()
                    _sd = _ss.get_static_data(symbol) if _ss else None
                    _fthg_s = float(_sd.get('FINAL_THG', 0) or 0) if _sd else 0
                except: _fthg_s = 0
            if metric.bid_buy_ucuzluk is not None and _fthg_s:
                _fbs = round(_fthg_s - 1000 * metric.bid_buy_ucuzluk, 2)
            if metric.ask_sell_pahalilik is not None and short_final:
                _fsas = round(short_final - 1000 * metric.ask_sell_pahalilik, 2)
            _spread = round(metric.ask - metric.bid, 4) if metric.bid and metric.ask else None
            logger.info(
                f"[ADDNEWPOS_DEBUG] SHORT {symbol}: metric_found=True, "
                f"fbtot={metric.fbtot}, sfstot={metric.sfstot}, gort={metric.gort}, "
                f"bid_buy_ucuzluk={metric.bid_buy_ucuzluk}, ask_sell_pahalilik={metric.ask_sell_pahalilik}, "
                f"bid={metric.bid}, ask={metric.ask}, last={metric.last}, "
                f"prev_close={metric.prev_close}, spread={_spread}, "
                f"SF={short_final:.0f}, Final_BS={_fbs}, Final_SAS={_fsas}"
            )
            
            # Null check
            if metric.ask_sell_pahalilik is None or metric.sfstot is None:
                logger.warning(
                    f"[ADDNEWPOS] ❌ {symbol}: METRIC NULL (SHORT) — "
                    f"ask_sell_pahalilik={metric.ask_sell_pahalilik}, sfstot={metric.sfstot}, "
                    f"bid={metric.bid}, ask={metric.ask}, last={metric.last} "
                    f"(SF={short_final:.0f})"
                )
                filtered_out.append(Decision(
                    symbol=symbol, action="FILTERED", filtered_out=True,
                    filter_reasons=[f"ask_sell={metric.ask_sell_pahalilik}, sfstot={metric.sfstot} (SF={short_final:.0f})"],
                    reject_reason_code=RejectReason.CRITICAL_METRIC_MISSING,
                    step_number=2, timestamp=datetime.now()
                ))
                continue
            
            ask_sell = metric.ask_sell_pahalilik
            sfstot = metric.sfstot
            
            # SFStot filtresi — düşük SFStot = grupta pahalı = iyi short
            if sfstot_lt is not None and sfstot >= sfstot_lt:
                logger.info(
                    f"[ADDNEWPOS] SHORT FILTERED {symbol}: SFStot {sfstot:.2f} >= {sfstot_lt} (not expensive enough for SHORT) "
                    f"| fbtot={metric.fbtot} gort={metric.gort} ucuz={metric.bid_buy_ucuzluk} pah={ask_sell:.4f} "
                    f"bid={metric.bid} ask={metric.ask} last={metric.last}"
                )
                filtered_out.append(Decision(
                    symbol=symbol, action="FILTERED", filtered_out=True,
                    filter_reasons=[f"SFStot={sfstot:.2f} >= {sfstot_lt} (SF={short_final:.0f})"],
                    reject_reason_code=RejectReason.VALUATION_TOO_POOR,
                    reject_reason_details={'value': sfstot, 'limit': sfstot_lt},
                    step_number=2, timestamp=datetime.now()
                ))
                continue
            
            # Pahalilik filtresi 
            if ask_sell_pahalilik_gt is not None and ask_sell <= ask_sell_pahalilik_gt:
                logger.info(
                    f"[ADDNEWPOS] SHORT FILTERED {symbol}: Pahalilik {ask_sell:.4f} <= {ask_sell_pahalilik_gt} (not expensive enough) "
                    f"| fbtot={metric.fbtot} sfstot={sfstot:.2f} gort={metric.gort} ucuz={metric.bid_buy_ucuzluk} "
                    f"bid={metric.bid} ask={metric.ask} last={metric.last}"
                )
                filtered_out.append(Decision(
                    symbol=symbol, action="FILTERED", filtered_out=True,
                    filter_reasons=[f"Pahalilik={ask_sell:.4f} <= {ask_sell_pahalilik_gt} (SF={short_final:.0f})"],
                    reject_reason_code=RejectReason.NOT_CHEAP_ENOUGH,
                    reject_reason_details={'value': ask_sell, 'limit': ask_sell_pahalilik_gt},
                    step_number=2, timestamp=datetime.now()
                ))
                continue
            
            # Existing position
            existing_qty = existing_map.get(symbol, 0)
            existing_short_qty = abs(existing_qty) if existing_qty < 0 else 0
            
            # No hardcoded max_lot_per_symbol — MinMaxArea handles todays_min_qty for shorts
            
            # Cooldown
            if cooldown_manager and not cooldown_manager.can_make_decision(symbol, snapshot_ts):
                filtered_out.append(Decision(
                    symbol=symbol, action="FILTERED", filtered_out=True,
                    filter_reasons=["Cooldown active"],
                    reject_reason_code=RejectReason.COOLDOWN_ACTIVE,
                    step_number=2, timestamp=datetime.now()
                ))
                continue
            
            # LOT: RECSIZE + MAXALW
            calculated_lot = self._calculate_lot_janall(
                symbol=symbol,
                recsize=recsize,
                existing_qty=existing_short_qty,
                metric=metric,
                total_portfolio_lots=total_portfolio_lots,
            )
            
            if calculated_lot <= 0:
                continue
            
            action = "ADD_SHORT" if existing_short_qty > 0 else "SHORT"
            
            # Confidence
            confidence = 0.5
            if confidence_calculator:
                dummy_pos = PositionSnapshot(
                    symbol=symbol, qty=-calculated_lot,
                    avg_price=metric.ask or 0, current_price=metric.ask or 0,
                    unrealized_pnl=0, timestamp=datetime.now()
                )
                confidence = confidence_calculator.calculate_confidence(
                    symbol=symbol, position=dummy_pos, metrics=metric,
                    action=action, reason="AddShort"
                )
            
            decision = Decision(
                symbol=symbol, action=action, order_type="ASK_SELL",
                lot_percentage=None, calculated_lot=calculated_lot,
                price_hint=metric.ask, step_number=2,
                reason=f"Pos:{int(existing_qty)} | SF={short_final:.0f} REC={recsize} SFStot={sfstot:.2f} pah={ask_sell:.4f} [{dosya}]",
                confidence=confidence,
                metrics_used={
                    'SHORT_FINAL': short_final, 'RECSIZE': recsize,
                    'ask_sell_pahalilik': ask_sell, 'sfstot': sfstot,
                    'DOSYA': dosya, 'existing_short_qty': existing_short_qty,
                },
                timestamp=datetime.now()
            )
            decisions.append(decision)
            logger.info(
                f"[ADDNEWPOS] ✅ SHORT PASSED {symbol}: {action} {calculated_lot} lot "
                f"| fbtot={metric.fbtot} sfstot={sfstot:.2f} gort={metric.gort} "
                f"ucuz={metric.bid_buy_ucuzluk} pah={ask_sell:.4f} "
                f"bid={metric.bid} ask={metric.ask} last={metric.last} "
                f"son5={metric.son5_tick} v1h={metric.volav_1h} v4h={metric.volav_4h} "
                f"SF={short_final:.0f} REC={recsize}"
            )
            
            if cooldown_manager:
                cooldown_manager.record_decision(symbol, snapshot_ts)
        
        logger.info(f"[ADDNEWPOS] AddShort: {len(decisions)} decisions, {len(filtered_out)} filtered")
        return decisions, filtered_out

    # ═══════════════════════════════════════════════════════════════════
    # LOT CALCULATION (Janall birebir)
    # ═══════════════════════════════════════════════════════════════════
    
    def _calculate_lot_janall(
        self,
        symbol: str,
        recsize: int,
        existing_qty: float,
        metric: SymbolMetrics,
        total_portfolio_lots: Optional[float] = None,
    ) -> int:
        """
        ADDNEWPOS lot hesabı — RAW lot (JFIN/MAXALW cap öncesi).
        
        1. RECSIZE (tumcsv'den — ntumcsvport.py tarafından hesaplanmış)
        2. calculate_rounded_lot ile yuvarla (min 200 for BUY)
        
        NOT: JFIN % ve MAXALW/4 cap XNL engine'de birlikte uygulanır:
          final = min(RECSIZE × JFIN%, MAXALW/4), min 200
        MinMax Area validasyonu da XNL engine'de ayrıca çalışır.
        """
        # RECSIZE'ı temel al — tumcsv'de zaten hesaplanmış:
        #   RECSIZE = (KUME_PREM * 8 + AVG_ADV/25) / 4, cap: AVG_ADV / 6
        base_lot = recsize
        
        # Strict rounding (min 200 for BUY)
        final_lot = calculate_rounded_lot(base_lot, self.lot_policy_config, existing_qty=0, action="BUY")
        
        return final_lot



    # ═══════════════════════════════════════════════════════════════════
    # LEGACY METHODS (backward compatibility — kullanılmıyor ama API uyumluluğu)
    # ═══════════════════════════════════════════════════════════════════
    
    def compute_lt_goodness(self, metric: SymbolMetrics, side: str = "LONG") -> float:
        """DEPRECATED: v3.0'da kullanılmıyor. Geriye uyumluluk için tutuldu."""
        return 50.0  # Sabit değer — artık karar mekanizmasını etkilemiyor
    
    def compute_mm_goodness(self, metric: SymbolMetrics) -> float:
        """DEPRECATED: v3.0'da kullanılmıyor."""
        return 50.0
    
    def pick_candidates_by_intent(self, candidates, intent, strategy="LT"):
        """DEPRECATED: v3.0'da tumcsv sıralaması kullanılıyor."""
        return candidates


# ============================================================================
# Global Instance Management
# ============================================================================

_addnewpos_engine: Optional[AddnewposEngine] = None


def get_addnewpos_engine():
    """Get global AddnewposEngine instance"""
    return _addnewpos_engine


def initialize_addnewpos_engine(config_path: Optional[Path] = None):
    """Initialize global AddnewposEngine instance"""
    global _addnewpos_engine
    _addnewpos_engine = AddnewposEngine(config_path)
    return _addnewpos_engine
