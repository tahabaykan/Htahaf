"""
Pattern Suggestions API Routes - v2
====================================
Dogrudan pipeline v5.1 sonuclarindan (v5_summary.csv) ve 
janalldata.csv baz ex-div tarihlerinden beslenir.

UI'daki "Pattern Suggestions" butonu bunu cagirir.
"""
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime, date, timedelta
import os
import json
import calendar

import pandas as pd
import numpy as np

from app.core.logger import logger

router = APIRouter(prefix="/api/pattern-suggestions", tags=["pattern_suggestions"])

EXCLUDED_PATH = Path(r"C:\StockTracker\quant_engine\data\pattern_suggestions_excluded.json")
BASE_DIR = Path(r"C:\StockTracker\quant_engine")
PIPELINE_DIR = BASE_DIR / "output" / "exdiv_v5"
STOCKTRACKER = Path(r"C:\StockTracker")
DRIFT_TOLERANCE = 4
NORM_DAYS = 30  # Return'leri 30 günlük standart süreye normalize et


def _sanitize_nan(obj):
    """Recursively replace NaN/Inf float values with None for JSON safety."""
    if isinstance(obj, dict):
        return {k: _sanitize_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_sanitize_nan(v) for v in obj]
    elif isinstance(obj, float):
        if obj != obj or obj == float('inf') or obj == float('-inf'):  # NaN or Inf
            return None
        return obj
    else:
        # numpy float types
        try:
            if hasattr(obj, 'item'):  # numpy scalar
                val = obj.item()
                if isinstance(val, float) and (val != val or val == float('inf') or val == float('-inf')):
                    return None
                return val
        except Exception:
            pass
        return obj


def _load_excluded() -> list:
    """Load excluded ticker list."""
    if EXCLUDED_PATH.exists():
        try:
            return json.loads(EXCLUDED_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_excluded(excluded: list):
    """Save excluded ticker list."""
    EXCLUDED_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXCLUDED_PATH.write_text(json.dumps(excluded, indent=2), encoding="utf-8")


def _load_base_exdiv():
    """janalldata.csv'den baz ex-div tarihlerini yukle."""
    base_map = {}
    jp = STOCKTRACKER / "janalldata.csv"
    if jp.exists():
        jdf = pd.read_csv(jp, encoding='latin-1')
        for _, row in jdf.iterrows():
            tk = str(row.get('PREF IBKR', '')).strip()
            exd = row.get('EX-DIV DATE', '')
            if tk and pd.notna(exd) and str(exd).strip():
                for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y']:
                    try:
                        base_map[tk] = pd.to_datetime(str(exd).strip(), format=fmt)
                        break
                    except:
                        pass
    return base_map


def _next_exdiv(ticker, base_map, today):
    """Sonraki ex-div projeksiyonu (janalldata baz)."""
    if ticker not in base_map:
        return None, None
    bd = base_map[ticker]

    # n=0: Baz tarihin kendisini de kontrol et (mevcut çeyrek)
    for n in range(0, 30):
        if n == 0:
            p = bd  # Baz tarih kendisi
        else:
            tm = bd.month + 3 * n
            ty = bd.year + (tm - 1) // 12
            tm = ((tm - 1) % 12) + 1
            md = calendar.monthrange(ty, tm)[1]
            ad = min(bd.day, md)
            try:
                p = pd.Timestamp(ty, tm, ad)
            except:
                continue
        if p + timedelta(days=DRIFT_TOLERANCE) >= today:
            return p, (p - today).days
    return None, None


def _biz_day_offset(base_dt, offset):
    """Is gunu offset hesapla."""
    dt = base_dt + timedelta(days=int(offset * 7 / 5))
    while dt.weekday() >= 5:
        dt += timedelta(days=1)
    return dt


def _build_suggestions(today=None):
    """
    Pipeline sonuclarindan guncel trade onerilerini olustur.
    Her oneri 'div-5' / 'div+3' formatinda entry/exit gosteriyor.
    """
    if today is None:
        today = pd.Timestamp(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0))

    sp = PIPELINE_DIR / "v5_summary.csv"
    if not sp.exists():
        return None, "Pipeline sonuclari yok. Once run_pipeline_v51.py calistirin."

    summary = pd.read_csv(sp)
    base_map = _load_base_exdiv()

    active_longs = []
    active_shorts = []
    upcoming_longs = []
    upcoming_shorts = []
    holding_longs = []
    holding_shorts = []

    for _, row in summary.iterrows():
        tk = row['ticker']
        nxt, days_until = _next_exdiv(tk, base_map, today)
        if nxt is None or days_until is None:
            continue

        exdiv_str = nxt.strftime('%Y-%m-%d')

        # ─── LONG ───
        if pd.notna(row.get('best_long_sharpe')) and row['best_long_sharpe'] > 0.3:
            if pd.notna(row.get('best_long_pval')) and row['best_long_pval'] <= 0.15:
                entry_off = int(row['best_long_entry']) if pd.notna(row.get('best_long_entry')) else -5
                exit_off = int(row['best_long_exit']) if pd.notna(row.get('best_long_exit')) else 0

                entry_dt = _biz_day_offset(nxt, entry_off)
                exit_dt = _biz_day_offset(nxt, exit_off)
                if exit_dt <= entry_dt:
                    exit_dt = entry_dt + timedelta(days=2)

                # SCORE: pattern gücü × zaman-normalize return bileşik skoru
                _wr = float(row.get('best_long_win', 0))
                _sh = float(row.get('best_long_sharpe', 0))
                _pv = float(row['best_long_pval']) if pd.notna(row.get('best_long_pval')) else 1.0
                _nc = int(row.get('n_exdivs', 0))
                _rt = float(row.get('best_long_ret', 0))
                _hold = max(3, exit_off - entry_off)  # iş günü olarak offset farkı
                _norm_rt = _rt / _hold * NORM_DAYS  # 30 günlük normalize return
                # Confidence bileşenleri (0-100)
                _conf = min(100, max(0,
                    _wr * 35 +                                    # Win rate (max 35)
                    (1 - min(_pv, 1)) * 25 +                      # p-value (max 25)
                    min(_nc, 10) / 10 * 20 +                      # Cycle sayısı (max 20, 10+ = tam)
                    min(_sh, 5) / 5 * 20                          # Sharpe (max 20, 5+ = tam)
                ))
                # Score = confidence × normalize return ağırlıklı
                score = round(_conf / 10 * (1 + abs(_norm_rt) / 3), 3)

                item = {
                    'ticker': tk,
                    'direction': 'LONG',
                    'strategy': str(row.get('best_long_name', '')),
                    'entry_date': entry_dt.strftime('%Y-%m-%d'),
                    'exit_date': exit_dt.strftime('%Y-%m-%d'),
                    'exdiv_date': exdiv_str,
                    'days_until_exdiv': int(days_until),
                    'entry_offset': entry_off,
                    'exit_offset': exit_off,
                    'entry_offset_label': f"div{entry_off:+d}",
                    'exit_offset_label': f"div{exit_off:+d}",
                    'cycle_label': f"Entry: div{entry_off:+d} → Exit: div{exit_off:+d}",
                    'holding_days': _hold,
                    'raw_return': round(_rt, 3),
                    'expected_return': round(_norm_rt, 3),  # 30 gün normalize
                    'win_rate': round(float(row.get('best_long_win', 0)), 3),
                    'sharpe': round(float(row.get('best_long_sharpe', 0)), 2),
                    'p_value': round(float(row.get('best_long_pval', 1)), 4),
                    'yield_pct': round(float(row.get('yield_pct', 0)), 1),
                    'n_exdivs': int(row.get('n_exdivs', 0)),
                    'score': round(score, 3),
                }

                win_start = entry_dt - timedelta(days=1)
                win_end = entry_dt + timedelta(days=1)
                days_to_exit = (exit_dt - today).days

                if win_start <= today <= win_end:
                    # Entry penceresi içinde — aktif
                    item['signal'] = 'BUY_NOW'
                    active_longs.append(item)
                elif entry_dt < today and exit_dt >= today and days_to_exit >= 2:
                    # Entry geçmiş ama exit'e 2+ gün var — hâlâ girilebilir
                    item['signal'] = 'BUY_NOW'
                    item['days_in'] = (today - entry_dt).days
                    item['days_to_exit'] = days_to_exit
                    active_longs.append(item)
                elif entry_dt < today and exit_dt >= today:
                    # Exit'e 2 günden az kalmış — sadece holding
                    item['signal'] = 'HOLDING'
                    item['days_in'] = (today - entry_dt).days
                    item['days_to_exit'] = days_to_exit
                    holding_longs.append(item)
                elif entry_dt > today and (entry_dt - today).days <= 30:
                    item['signal'] = 'UPCOMING'
                    item['days_to_entry'] = (entry_dt - today).days
                    upcoming_longs.append(item)

        # ─── SHORT ───
        if pd.notna(row.get('best_short_sharpe')) and row['best_short_sharpe'] > 0.3:
            if pd.isna(row.get('best_short_pval')) or row['best_short_pval'] > 0.15:
                continue
            short_entry_off = int(row['best_short_entry']) if pd.notna(row.get('best_short_entry')) else 0
            short_exit_off = int(row['best_short_exit']) if pd.notna(row.get('best_short_exit')) else 5

            entry_dt = _biz_day_offset(nxt, short_entry_off)
            exit_dt = _biz_day_offset(nxt, short_exit_off)
            if exit_dt <= entry_dt:
                exit_dt = entry_dt + timedelta(days=2)

            # SCORE: pattern gücü × zaman-normalize return bileşik skoru
            _wr = float(row['best_short_win']) if pd.notna(row.get('best_short_win')) else 0
            _sh = float(row.get('best_short_sharpe', 0))
            _pv = float(row['best_short_pval']) if pd.notna(row.get('best_short_pval')) else 1.0
            _nc = int(row.get('n_exdivs', 0))
            _rt = float(row.get('best_short_ret', 0))
            _hold = max(3, short_exit_off - short_entry_off)  # iş günü olarak offset farkı
            _norm_rt = _rt / _hold * NORM_DAYS  # 30 günlük normalize return
            _conf = min(100, max(0,
                _wr * 35 +
                (1 - min(_pv, 1)) * 25 +
                min(_nc, 10) / 10 * 20 +
                min(_sh, 5) / 5 * 20
            ))
            score = round(_conf / 10 * (1 + abs(_norm_rt) / 3), 3)

            item = {
                'ticker': tk,
                'direction': 'SHORT',
                'strategy': str(row.get('best_short_name', 'WASHOUT')),
                'entry_date': entry_dt.strftime('%Y-%m-%d'),
                'exit_date': exit_dt.strftime('%Y-%m-%d'),
                'exdiv_date': exdiv_str,
                'days_until_exdiv': int(days_until),
                'entry_offset': short_entry_off,
                'exit_offset': short_exit_off,
                'entry_offset_label': f"div{short_entry_off:+d}",
                'exit_offset_label': f"div{short_exit_off:+d}",
                'cycle_label': f"Entry: div{short_entry_off:+d} → Exit: div{short_exit_off:+d}",
                'holding_days': _hold,
                'raw_return': round(_rt, 3),
                'expected_return': round(_norm_rt, 3),  # 30 gün normalize
                'win_rate': round(float(row['best_short_win']) if pd.notna(row.get('best_short_win')) else 0, 3),
                'sharpe': round(float(row.get('best_short_sharpe', 0)), 2),
                'p_value': round(float(row['best_short_pval']) if pd.notna(row.get('best_short_pval')) else 1.0, 4),
                'yield_pct': round(float(row.get('yield_pct', 0)), 1),
                'n_exdivs': int(row.get('n_exdivs', 0)),
                'score': round(score, 3),
            }

            win_start = entry_dt - timedelta(days=1)
            win_end = entry_dt + timedelta(days=1)
            days_to_exit = (exit_dt - today).days

            if win_start <= today <= win_end:
                # Entry penceresi içinde — aktif
                item['signal'] = 'SHORT_NOW'
                active_shorts.append(item)
            elif entry_dt < today and exit_dt >= today and days_to_exit >= 2:
                # Entry geçmiş ama exit'e 2+ gün var — hâlâ girilebilir
                item['signal'] = 'SHORT_NOW'
                item['days_in'] = (today - entry_dt).days
                item['days_to_exit'] = days_to_exit
                active_shorts.append(item)
            elif entry_dt < today and exit_dt >= today:
                # Exit'e 2 günden az kalmış — sadece holding
                item['signal'] = 'HOLDING_SHORT'
                item['days_in'] = (today - entry_dt).days
                item['days_to_exit'] = days_to_exit
                holding_shorts.append(item)
            elif entry_dt > today and (entry_dt - today).days <= 30:
                item['signal'] = 'UPCOMING_SHORT'
                item['days_to_entry'] = (entry_dt - today).days
                upcoming_shorts.append(item)

    active_longs.sort(key=lambda x: x['score'], reverse=True)
    active_shorts.sort(key=lambda x: x['score'], reverse=True)
    holding_longs.sort(key=lambda x: x['score'], reverse=True)
    holding_shorts.sort(key=lambda x: x['score'], reverse=True)
    upcoming_longs.sort(key=lambda x: (x.get('days_to_entry', 999), -x['score']))
    upcoming_shorts.sort(key=lambda x: (x.get('days_to_entry', 999), -x['score']))

    # ── CONFLICT RESOLUTION: Aynı ticker hem LONG hem SHORT olamaz ──
    # Active listelerinde çakışma varsa, yüksek skorlu kazanır
    long_tickers = {t['ticker']: t for t in active_longs}
    short_tickers = {t['ticker']: t for t in active_shorts}
    conflicting = set(long_tickers.keys()) & set(short_tickers.keys())
    for tk in conflicting:
        l_score = long_tickers[tk]['score']
        s_score = short_tickers[tk]['score']
        if l_score >= s_score:
            # LONG kazanır — SHORT'u sil
            active_shorts = [s for s in active_shorts if s['ticker'] != tk]
            logger.info(
                f"[PatternSuggestions] CONFLICT {tk}: LONG(score={l_score:.1f}) "
                f"vs SHORT(score={s_score:.1f}) → LONG wins"
            )
        else:
            # SHORT kazanır — LONG'u sil
            active_longs = [l for l in active_longs if l['ticker'] != tk]
            logger.info(
                f"[PatternSuggestions] CONFLICT {tk}: SHORT(score={s_score:.1f}) "
                f"vs LONG(score={l_score:.1f}) → SHORT wins"
            )

    return {
        'active_longs': active_longs,
        'active_shorts': active_shorts,
        'holding_longs': holding_longs,
        'holding_shorts': holding_shorts,
        'upcoming_longs': upcoming_longs,
        'upcoming_shorts': upcoming_shorts,
    }, None


def _enrich_with_qe_data(trades: List[Dict]) -> List[Dict]:
    """Enrich trade suggestions with quant-engine live data."""
    try:
        # Primary source: DataFabric (has both static + live merged data)
        from app.core.data_fabric import get_data_fabric
        fabric = get_data_fabric()
        
        # Get all fast snapshots (static + L1 + derived scores)
        fast_data = {}
        if fabric:
            try:
                fast_data = fabric.get_all_fast_snapshots() or {}
            except Exception:
                pass
        
        # Fallback: static data from StaticDataStore
        static_store = None
        try:
            from app.market_data.static_data_store import get_static_store
            static_store = get_static_store()
        except Exception:
            pass
        
        # L1 cache for bid/ask/last
        l1_cache = {}
        try:
            from app.api.market_data_routes import market_data_cache
            l1_cache = market_data_cache or {}
        except Exception:
            pass
        
        for t in trades:
            ticker = t['ticker']
            
            # Try DataFabric first (richest source)
            qe = fast_data.get(ticker, {})
            
            # Static fields (Fbtot, SFStot, GORT, etc.)
            t['FINAL_THG'] = qe.get('FINAL_THG') or qe.get('fbtot')
            t['Fbtot'] = qe.get('fbtot') or qe.get('Fbtot')
            t['SFStot'] = qe.get('sfstot') or qe.get('SFStot')
            t['GORT'] = qe.get('gort') or qe.get('GORT')
            t['SMA63chg'] = qe.get('sma63_chg') or qe.get('SMA63chg') or qe.get('SMA63 chg')
            t['SMI'] = qe.get('SMI') or qe.get('smi')
            t['Final_BB'] = qe.get('Final_BB_skor')
            t['Final_SAS'] = qe.get('Final_SAS_skor')
            
            # L1 data (bid/ask/last)
            l1 = l1_cache.get(ticker, {})
            t['bid'] = qe.get('bid') or l1.get('bid')
            t['ask'] = qe.get('ask') or l1.get('ask')
            t['last'] = qe.get('last') or l1.get('last') or l1.get('price')
            t['prev_close'] = qe.get('prev_close') or l1.get('prev_close')
            
            # Fallback: StaticDataStore for missing fields
            if static_store and static_store.is_loaded():
                if t.get('Fbtot') is None or t.get('SFStot') is None:
                    sd = static_store.get_static_data(ticker)
                    if sd:
                        if t.get('FINAL_THG') is None:
                            t['FINAL_THG'] = sd.get('FINAL_THG')
                        if t.get('Fbtot') is None:
                            t['Fbtot'] = sd.get('FINAL_THG')  # Fbtot = FINAL_THG
                        if t.get('SFStot') is None:
                            t['SFStot'] = sd.get('SHORT_FINAL')
                        if t.get('GORT') is None:
                            t['GORT'] = sd.get('GORT')
                        if t.get('SMA63chg') is None:
                            t['SMA63chg'] = sd.get('SMA63 chg')
                        if t.get('SMI') is None:
                            t['SMI'] = sd.get('SMI')
                            
    except Exception as e:
        logger.warning(f"[PatternSuggestions] Could not enrich with QE data: {e}")
    return trades


def _normalize_trade(t, today_ts):
    """Her trade item'ını frontend-uyumlu formata dönüştür."""
    signal = t.get('signal', '')
    direction = t.get('direction', '')

    # Action label (UI'da gösterilecek)
    action_map = {
        'BUY_NOW': '🟢 BUY',
        'HOLDING': '📦 HOLD',
        'UPCOMING': '⏳ UPCOMING',
        'SHORT_NOW': '🔴 SHORT',
        'HOLDING_SHORT': '📦 COVER WATCH',
        'UPCOMING_SHORT': '⏳ UPCOMING SHORT',
    }
    t['action_label'] = action_map.get(signal, signal)

    # Held status (pipeline v5'te yok, HELD kabul et)
    if 'held_status' not in t:
        t['held_status'] = 'HELD'

    # return_pct (frontend bu ismi bekliyor)
    # expected_return zaten % cinsinden (ör: 3.51 = %3.51), tekrar ×100 YAPMA
    if 'return_pct' not in t:
        t['return_pct'] = round(t.get('expected_return', 0), 2)

    # win_rate yüzde olarak (0-100)
    wr = t.get('win_rate', 0)
    if wr is not None and wr <= 1:
        t['win_rate'] = round(wr * 100, 1)
    else:
        t['win_rate'] = round(wr or 0, 1)

    # ─── CONFIDENCE: Pattern güvenilirliği (0-100) ───
    # 4 bileşen: Win Rate, p-value, Cycle sayısı, Sharpe
    wr_raw = t.get('win_rate', 0) or 0
    # win_rate bu noktada 0-100 arası (üstte ×100 yapıldı)
    wr_frac = min(wr_raw / 100, 1.0)  # 0-1 arası
    sharpe = t.get('sharpe', 0) or 0
    pval = t.get('p_value')
    if pval is None:
        pval = 1.0
    n_cycles = t.get('n_exdivs', 0) or 0

    confidence = min(100, max(0,
        wr_frac * 35 +                             # Win rate (max 35p) - en önemli
        (1 - min(pval, 1)) * 25 +                  # p-value (max 25p) - istatistik
        min(n_cycles, 10) / 10 * 20 +              # Cycle sayısı (max 20p) - veri miktarı
        min(sharpe, 5) / 5 * 20                    # Sharpe (max 20p) - tutarlılık
    ))
    t['confidence_pct'] = round(confidence, 1)

    # Progress & days_remaining
    try:
        entry_dt = pd.Timestamp(t.get('entry_date', ''))
        exit_dt = pd.Timestamp(t.get('exit_date', ''))
        total_days = max(1, (exit_dt - entry_dt).days)
        elapsed = max(0, (today_ts - entry_dt).days)
        t['progress_pct'] = round(min(100, max(0, elapsed / total_days * 100)), 1)
        t['days_remaining'] = max(0, (exit_dt - today_ts).days)
    except Exception:
        t['progress_pct'] = 0
        t['days_remaining'] = t.get('holding_days', 0)

    # Score rank label (yeni skalaya uygun)
    score = t.get('score', 0) or 0
    if score >= 9:
        t['score_label'] = '🔥 Strong'
    elif score >= 6:
        t['score_label'] = '⚡ Good'
    else:
        t['score_label'] = '📊 Moderate'

    return t


@router.get("/active")
async def get_active_suggestions(target_date: Optional[str] = None):
    """
    Pipeline v5.1 sonuclarindan bugunun trade onerilerini getir.

    Her oneri icin:
    - action_label: "🟢 BUY", "📦 HOLD", "🔴 SHORT", "📦 COVER WATCH", "⏳ UPCOMING"
    - direction: LONG veya SHORT
    - return_pct, win_rate, confidence_pct, progress_pct, days_remaining
    - entry/exit tarih, exdiv tarih, score, strategy
    - QE verileri: FINAL_THG, Fbtot, SFStot, GORT, SMA63chg, SMI
    """
    try:
        if target_date:
            today_ts = pd.Timestamp(target_date)
        else:
            today_ts = pd.Timestamp(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0))
            # Weekend -> advance to Monday
            if today_ts.weekday() >= 5:
                today_ts += timedelta(days=(7 - today_ts.weekday()))

        data, err = _build_suggestions(today_ts)
        if err:
            raise HTTPException(status_code=404, detail=err)

        # Tum kategorileri birleştir
        all_trades = (
            data['active_longs'] + data['active_shorts'] +
            data['holding_longs'] + data['holding_shorts'] +
            data['upcoming_longs'] + data['upcoming_shorts']
        )

        # QE verisiyle zenginleştir
        all_trades = _enrich_with_qe_data(all_trades)

        # Her trade'i normalize et
        for t in all_trades:
            _normalize_trade(t, today_ts)

        # Exclusion uygula
        excluded_keys = _load_excluded()
        included = []
        excluded = []

        for t in all_trades:
            key = f"{t['ticker']}_{t['direction']}_{t['entry_date']}"
            if key in excluded_keys:
                t['excluded'] = True
                excluded.append(t)
            else:
                t['excluded'] = False
                included.append(t)

        # Score'a göre sırala (yüksekten düşüğe)
        included.sort(key=lambda x: x.get('score', 0) or 0, reverse=True)
        excluded.sort(key=lambda x: x.get('score', 0) or 0, reverse=True)

        # İstatistikler
        total_longs = len([t for t in included if t['direction'] == 'LONG'])
        total_shorts = len([t for t in included if t['direction'] == 'SHORT'])
        buy_now = len([t for t in included if t.get('signal') in ('BUY_NOW', 'SHORT_NOW')])
        holding = len([t for t in included if t.get('signal') in ('HOLDING', 'HOLDING_SHORT')])
        upcoming = len([t for t in included if t.get('signal') in ('UPCOMING', 'UPCOMING_SHORT')])

        response = {
            'success': True,
            'target_date': today_ts.strftime('%Y-%m-%d'),
            'source': 'pipeline_v51_janalldata',

            # Frontend'in beklediği birleşik listeler
            'included': included,
            'included_count': len(included),
            'excluded': excluded,
            'excluded_count': len(excluded),

            # Geriye uyumluluk
            'active_count': buy_now,
            'active_longs': [t for t in included if t['direction'] == 'LONG' and t.get('signal') in ('BUY_NOW',)],
            'active_shorts': [t for t in included if t['direction'] == 'SHORT' and t.get('signal') in ('SHORT_NOW',)],
            'holding_longs': [t for t in included if t['direction'] == 'LONG' and t.get('signal') == 'HOLDING'],
            'holding_shorts': [t for t in included if t['direction'] == 'SHORT' and t.get('signal') == 'HOLDING_SHORT'],
            'upcoming_longs': [t for t in included if t['direction'] == 'LONG' and t.get('signal') == 'UPCOMING'],
            'upcoming_shorts': [t for t in included if t['direction'] == 'SHORT' and t.get('signal') == 'UPCOMING_SHORT'],

            # Toplam istatistikler
            'total_trades_in_report': len(included) + len(excluded),
            'stats': {
                'total_long_candidates': total_longs,
                'total_short_candidates': total_shorts,
                'buy_now': buy_now,
                'holding': holding,
                'upcoming': upcoming,
            }
        }
        # Sanitize NaN/Inf values that break JSON serialization
        return _sanitize_nan(response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PatternSuggestions] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/exclude")
async def exclude_suggestion(ticker: str, direction: str, entry_date: str):
    """Add a trade to the excluded list."""
    try:
        excluded = _load_excluded()
        key = f"{ticker}_{direction}_{entry_date}"
        if key not in excluded:
            excluded.append(key)
            _save_excluded(excluded)
        return {'success': True, 'excluded_count': len(excluded)}
    except Exception as e:
        logger.error(f"[PatternSuggestions] Exclude error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/include")
async def include_suggestion(ticker: str, direction: str, entry_date: str):
    """Remove a trade from the excluded list (re-include)."""
    try:
        excluded = _load_excluded()
        key = f"{ticker}_{direction}_{entry_date}"
        if key in excluded:
            excluded.remove(key)
            _save_excluded(excluded)
        return {'success': True, 'excluded_count': len(excluded)}
    except Exception as e:
        logger.error(f"[PatternSuggestions] Include error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/exclude/reset")
async def reset_excluded():
    """Clear all excluded suggestions."""
    try:
        _save_excluded([])
        return {'success': True, 'excluded_count': 0}
    except Exception as e:
        logger.error(f"[PatternSuggestions] Reset error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
